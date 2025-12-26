# smart_extractor.py
import re
import requests
import concurrent.futures
import time
import random
from googlesearch import search
from bs4 import BeautifulSoup
from urllib.parse import urljoin

class SmartExtractor:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        
        # [수정] 지역번호/식별번호 확장 (050, 0505 등 안심번호 포함)
        # 02, 03x~06x, 010~019, 070, 050x, 080
        self.area_code_pattern = r"(?:02|0[3-6]\d|01[016789]|070|050\d?|080)"

        # [수정] 전화번호 정규식 개선
        # 1. 구분자(hyphen, dot, space)가 있거나
        # 2. 구분자 없이 붙여쓴 경우(단, 9~11자리 길이 제한)
        self.phone_regex = re.compile(r"""
            (?<!\d) # 앞에 숫자가 없어야 함
            (?:
                # 패턴 A: 국제전화 (+82)
                (?:\+|00)82[\s\.\-]*\(?0?\)?[\s\.\-]*
                (?P<intl_area>\d{2,3})
                [\s\.\-\)]*
                (?P<intl_mid>\d{3,4})
                [\s\.\-]*
                (?P<intl_end>\d{4})
                |
                # 패턴 B: 국내전화 (구분자 있는 경우: 02-123-4567)
                (?P<dom_area_sep>""" + self.area_code_pattern + r""")
                [\s\.\-\)]+
                (?P<dom_mid_sep>\d{3,4})
                [\s\.\-]+
                (?P<dom_end_sep>\d{4})
                |
                # 패턴 C: 국내전화 (붙여쓴 경우: 01012345678, 021234567)
                # 오탐 방지를 위해 지역번호 패턴을 엄격하게 적용
                (?P<dom_area_raw>""" + self.area_code_pattern + r""")
                (?P<dom_mid_raw>\d{3,4})
                (?P<dom_end_raw>\d{4})
            )
            (?!\d) # 뒤에 숫자가 없어야 함
        """, re.VERBOSE)
        
        self.fax_keywords = ['fax', 'facsimile', 'f.', 'f:', 'fx', '팩스']
        
        # [수정] 오탐 방지용 부정 키워드 (계좌, 사업자번호 등)
        self.negative_keywords = [
            '계좌', '은행', '예금', 'bank', 'account', 'iban', 'swift', '예금주',
            '사업자', '등록번호', 'price', 'date', '202' # 날짜(202x년) 오탐 방지
        ]

        self.blocked_domains = [
            'facebook.com', 'instagram.com', 'jobkorea.co.kr', 'saramin.co.kr', 
            'jobplanet.co.kr', 'buykorea.org', 'incruit.com', 'catch.co.kr', 
            'work.go.kr', 'linkedin.com', 'youtube.com', 'namu.wiki', 'nicebiz', 'kedkorea',
            'crediv.co.kr', 'kisreport.com', 'blog.naver.com'
        ]

    def search_google(self, company_name):
        try:
            time.sleep(random.uniform(1.0, 2.5))
            query = f"{company_name}"
            # [참고] google 라이브러리는 차단 위험이 높으므로, 실제 운영 시에는 주의 필요
            results = search(query, num_results=5, lang="ko")
            
            checked_count = 0
            for url in results:
                if checked_count >= 3: return ""
                if any(blocked in url for blocked in self.blocked_domains):
                    checked_count += 1
                    continue
                return url
        except Exception:
            return ""
        return ""

    def get_text_with_frames(self, soup, base_url):
        text_content = ""
        try:
            frames = soup.select('frame, iframe')
            if not frames: return ""
            for frame in frames:
                src = frame.get('src')
                if not src: continue
                frame_url = urljoin(base_url, src)
                try:
                    frame_resp = requests.get(frame_url, headers=self.headers, timeout=5)
                    if frame_resp.status_code == 200:
                        frame_soup = BeautifulSoup(frame_resp.text, 'html.parser')
                        text_content += " " + frame_soup.get_text(separator=' ', strip=True)
                except: pass
        except: pass
        return text_content

    def normalize_phone(self, area, mid, end):
        """전화번호 포맷 통일 (0XX-XXXX-XXXX)"""
        return f"{area}-{mid}-{end}"

    def extract_links_from_soup(self, soup, info_dict):
        """[추가] HTML 태그(href)에서 전화번호/이메일 직접 추출"""
        if not soup: return

        # 1. tel: 링크 추출 (가장 정확함)
        for a in soup.select('a[href^="tel:"]'):
            href = a.get('href', '')
            raw_num = href.replace('tel:', '').strip()
            # 숫자 외 문자 제거
            clean_num = re.sub(r'[^0-9]', '', raw_num)
            
            # 국내 번호 포맷팅 시도 (단순 포맷팅)
            if len(clean_num) >= 9 and len(clean_num) <= 11:
                # 02-xxxx-xxxx or 010-xxxx-xxxx
                if clean_num.startswith('02') and len(clean_num) >= 9:
                    fmt_num = f"{clean_num[:2]}-{clean_num[2:-4]}-{clean_num[-4:]}"
                    info_dict['tel'].add(fmt_num)
                elif len(clean_num) >= 10:
                    fmt_num = f"{clean_num[:3]}-{clean_num[3:-4]}-{clean_num[-4:]}"
                    info_dict['tel'].add(fmt_num)

        # 2. mailto: 링크 추출
        for a in soup.select('a[href^="mailto:"]'):
            href = a.get('href', '')
            raw_mail = href.replace('mailto:', '').split('?')[0].strip()
            if '@' in raw_mail:
                 info_dict['email'].add(raw_mail)

    def extract_info_from_text(self, text, info_dict):
        if not text: return
        
        text_lower = text.lower()
        
        # 이메일 추출
        emails = self.email_pattern.findall(text)
        for email in emails:
            if not any(ext in email.lower() for ext in ['.png', '.jpg', '.gif', '.js', 'w3.org', 'example', 'sentry', 'u003e', '.css']):
                info_dict['email'].add(email)

        # 전화번호 추출
        matches = self.phone_regex.finditer(text_lower)
        for match in matches:
            groups = match.groupdict()
            
            area, mid, end = "", "", ""

            if groups['intl_area']: # 패턴 A: 국제/복합
                area, mid, end = groups['intl_area'], groups['intl_mid'], groups['intl_end']
                # 국제전화 코드(82) 처리: 0을 붙여줌 (예: 82-10 -> 010)
                if not area.startswith('0'): area = '0' + area

            elif groups['dom_area_sep']: # 패턴 B: 구분자 있음
                area, mid, end = groups['dom_area_sep'], groups['dom_mid_sep'], groups['dom_end_sep']

            elif groups['dom_area_raw']: # 패턴 C: 붙여씀
                area, mid, end = groups['dom_area_raw'], groups['dom_mid_raw'], groups['dom_end_raw']
            
            # 유효성 검사 (국번 길이 등)
            if not (2 <= len(area) <= 4 and 3 <= len(mid) <= 4 and len(end) == 4):
                continue
            
            full_number = self.normalize_phone(area, mid, end)
            
            # 컨텍스트 기반 필터링 (오탐 방지)
            start_pos = match.start()
            # 앞뒤 30글자 확인
            context_prev = text_lower[max(0, start_pos - 30):start_pos]
            context_next = text_lower[match.end():min(len(text_lower), match.end() + 10)] # 뒤쪽도 살짝 확인 (unit 등)

            combined_context = context_prev + " " + context_next
            
            # 부정 키워드(계좌, 날짜 등)가 있으면 스킵
            if any(k in combined_context for k in self.negative_keywords):
                continue

            # 팩스 키워드 확인
            if any(keyword in context_prev for keyword in self.fax_keywords):
                info_dict['fax'].add(full_number)
            else:
                info_dict['tel'].add(full_number)

    def extract_from_url(self, url):
        info = {'email': set(), 'tel': set(), 'fax': set()}
        
        if not url: return False, info
        if not url.startswith('http'): url = 'http://' + url

        try:
            resp = requests.get(url, headers=self.headers, timeout=15)
            resp.encoding = resp.apparent_encoding 
            
            if resp.status_code != 200: return False, info

            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # [추가] HTML 태그에서 링크 정보(tel:, mailto:) 우선 추출
            self.extract_links_from_soup(soup, info)
            
            visible_text = soup.get_text(separator=' ', strip=True)
            frame_text = self.get_text_with_frames(soup, url)
            
            # Raw Source (JS 변수 등 포함)
            raw_source_text = resp.text 

            combined_text = f"{visible_text} {frame_text} {raw_source_text}"
            
            self.extract_info_from_text(combined_text, info)
                    
            return True, info

        except Exception:
            return False, info

    def process_company(self, company_data):
        comp_name = company_data.get('기업명', '')
        url = company_data.get('홈페이지', '')

        clean_url = str(url).strip().lower()
        is_invalid_url = (not url) or (url == "-") or (clean_url in ['http://', 'https://', ''])
        
        if is_invalid_url:
            found_url = self.search_google(comp_name)
            if found_url:
                url = found_url
                company_data['홈페이지'] = url

        success = False
        contact_info = {'email': set(), 'tel': set(), 'fax': set()}

        if url:
            success, contact_info = self.extract_from_url(url)
            if not success:
                new_url = self.search_google(comp_name)
                if new_url and new_url != url:
                    url = new_url
                    company_data['홈페이지'] = new_url
                    success, contact_info = self.extract_from_url(new_url)

        # 기존 데이터 보존 및 병합
        existing_email = company_data.get('이메일', '')
        if existing_email: contact_info['email'].add(existing_email)
        if contact_info['email']:
            company_data['이메일'] = ", ".join(sorted(list(contact_info['email'])))[:300]

        existing_tel = company_data.get('전화번호', '')
        if existing_tel: contact_info['tel'].add(existing_tel)
        if contact_info['tel']:
            company_data['전화번호'] = ", ".join(sorted(list(contact_info['tel'])))[:100]

        # 팩스 정보가 새로 발견되면 업데이트
        existing_fax = company_data.get('팩스', '')
        if existing_fax: contact_info['fax'].add(existing_fax)
        if contact_info['fax']:
            company_data['팩스'] = ", ".join(sorted(list(contact_info['fax'])))[:100]

        return company_data

    def process_batch(self, data_list, max_workers=10):
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(self.process_company, data_list))
        return results