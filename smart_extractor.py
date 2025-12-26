# smart_extractor.py
import re
import requests
import concurrent.futures
from googlesearch import search
from bs4 import BeautifulSoup  # [추가] HTML 파싱을 위해 필요

class SmartExtractor:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/100.0.4896.127 Safari/537.36',
        }
        
        # 1. 이메일 패턴 (특수문자 포함 도메인 완벽 지원)
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        
        # 2. 전화번호/팩스 패턴 (02-1234-5678, 032-123-4567 등)
        # 괄호(본사) 같은 문자가 붙어있어도 번호만 깔끔하게 떼어내도록 설계
        self.phone_pattern = re.compile(r'(0\d{1,2})[\s\.\-\)]*(\d{3,4})[\s\.\-]*(\d{4})')

        # 3. 팩스 판단 키워드
        self.fax_keywords = ['fax', 'facsimile', 'f.', 'f:', 'fx', '팩스']

    def search_google(self, company_name):
        try:
            query = f"{company_name} 공식 홈페이지" 
            results = search(query, num_results=1, lang="ko")
            for url in results: return url
        except: return ""
        return ""

    def extract_from_url(self, url):
        info = {'email': set(), 'tel': set(), 'fax': set()}
        
        if not url: return info
        if not url.startswith('http'): url = 'http://' + url

        try:
            resp = requests.get(url, headers=self.headers, timeout=5)
            resp.encoding = resp.apparent_encoding 
            if resp.status_code != 200: return info
            
            # [핵심 변경] HTML 태그를 먼저 제거하고 '순수 텍스트'만 추출합니다.
            # separator=' '를 줘서 <span>TEL</span>02... 가 붙지 않고 떨어지게 만듦
            soup = BeautifulSoup(resp.text, 'html.parser')
            text_content = soup.get_text(separator=' ', strip=True)
            
            # 대소문자 통일 (검색 용이성)
            text_lower = text_content.lower()
            
            # 1. 이메일 추출
            emails = self.email_pattern.findall(text_content) # 이메일은 대소문자 유지
            for email in emails:
                # 이미지 파일명 등 노이즈 제거
                if not any(ext in email.lower() for ext in ['.png', '.jpg', '.gif', '.js', '.css', 'sentry', 'w3.org']):
                    info['email'].add(email)

            # 2. 전화번호/팩스 추출 및 분류 logic
            # 정규식으로 찾은 매치 오브젝트들을 순회
            matches = self.phone_pattern.finditer(text_lower)
            
            for match in matches:
                # 번호 조합 (02 + 1234 + 5678) -> 02-1234-5678
                full_number = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                
                # [위치 기반 문맥 파악]
                # 해당 번호가 발견된 위치(start_pos) 앞쪽 50글자를 봅니다.
                start_pos = match.start()
                context_window = text_lower[max(0, start_pos - 50):start_pos]
                
                # 팩스 키워드가 근처에 있으면 팩스로 분류
                if any(keyword in context_window for keyword in self.fax_keywords):
                    info['fax'].add(full_number)
                else:
                    info['tel'].add(full_number)

        except Exception as e:
            # print(f"Error extracting {url}: {e}")
            pass
            
        return info

    def process_company(self, company_data):
        comp_name = company_data.get('기업명', '')
        url = company_data.get('홈페이지', '')

        if not url or url == "-" or url == "":
            found_url = self.search_google(comp_name)
            if found_url:
                url = found_url
                company_data['홈페이지'] = url

        contact_info = {'email': set(), 'tel': set(), 'fax': set()}
        if url:
            contact_info = self.extract_from_url(url)

        # 데이터 병합 (중복 제거 및 정렬)
        existing_email = company_data.get('이메일', '')
        if existing_email: contact_info['email'].add(existing_email)
        
        if contact_info['email']:
            # 길이가 짧은 순, 혹은 알파벳 순으로 정렬해서 깔끔하게 저장
            sorted_emails = sorted(list(contact_info['email']))
            company_data['이메일'] = ", ".join(sorted_emails)[:300] # 너무 길면 적당히 자름 (GAS 오류 방지)

        existing_tel = company_data.get('전화번호', '')
        if existing_tel: contact_info['tel'].add(existing_tel)
        
        if contact_info['tel']:
            sorted_tels = sorted(list(contact_info['tel']))
            company_data['전화번호'] = ", ".join(sorted_tels)[:100]

        # 팩스는 발견된 것 중 최대 2개만
        if contact_info['fax']:
            sorted_faxes = sorted(list(contact_info['fax']))
            company_data['팩스'] = ", ".join(sorted_faxes)[:50]

        return company_data

    def process_batch(self, data_list, max_workers=10):
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(self.process_company, data_list))
        return results