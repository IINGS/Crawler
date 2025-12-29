# smart_extractor.py
import re
import requests
import concurrent.futures
import time
import random
#from googlesearch import search
from bs4 import BeautifulSoup
from urllib.parse import urljoin

class SmartExtractor:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        
        # 국내 국번 제한 (011~019 제외, 010만 허용)
        # 02, 03x~06x, 010, 070, 050x, 080
        self.area_code_pattern = r"(?:02|0[3-6]\d|010|070|050\d?|080)"

        # 전화번호 정규식 (대표번호 패턴 복구 + 010 제한 적용)
        self.phone_regex = re.compile(r"""
            (?<!\d) # 앞에 숫자가 없어야 함
            (?:
                # 패턴 A: 국제전화 (+82) - 여기서는 011 등도 허용 (예외 처리)
                (?:\+|00)82[\s\.\-]*\(?0?\)?[\s\.\-]*
                (?P<intl_area>\d{2,3})
                [\s\.\-\)]*
                (?P<intl_mid>\d{3,4})
                [\s\.\-]*
                (?P<intl_end>\d{4})
                |
                # 패턴 B: 전국 대표번호 (15xx, 16xx, 18xx)
                # 예: 1522-1131, 1588-7000, 1688-2934, 1899-3278
                (?P<rep_head>(?:15|16|18)\d{2})
                [\s\.\-]*
                (?P<rep_tail>\d{4})
                |
                # 패턴 C: 국내전화 (구분자 있는 경우: 02-123-4567)
                (?P<dom_area_sep>""" + self.area_code_pattern + r""")
                [\s\.\-\)]+
                (?P<dom_mid_sep>\d{3,4})
                [\s\.\-]+
                (?P<dom_end_sep>\d{4})
                |
                # 패턴 D: 국내전화 (붙여쓴 경우: 01012345678)
                (?P<dom_area_raw>""" + self.area_code_pattern + r""")
                (?P<dom_mid_raw>\d{3,4})
                (?P<dom_end_raw>\d{4})
            )
            (?!\d) # 뒤에 숫자가 없어야 함
        """, re.VERBOSE)
        
        self.fax_keywords = ['fax', 'facsimile', 'f.', 'f:', 'fx', '팩스']
        
        self.negative_keywords = [
            '계좌', '은행', '예금', 'bank', 'account', 'iban', 'swift', '예금주',
            '사업자', '등록번호', 'price', 'date', '202'
        ]

        self.blocked_domains = [
            'facebook.com', 'instagram.com', 'jobkorea.co.kr', 'saramin.co.kr', 
            'jobplanet.co.kr', 'buykorea.org', 'incruit.com', 'catch.co.kr', 
            'work.go.kr', 'linkedin.com', 'youtube.com', 'namu.wiki', 'nicebiz', 'kedkorea',
            'crediv.co.kr', 'kisreport.com', 'blog.naver.com'
        ]

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

    def get_js_content(self, soup, base_url):
        js_text = ""
        try:
            scripts = soup.select('script[src]')
            for script in scripts:
                src = script.get('src')
                if not src: continue
                
                # 외부 광고/추적 스크립트 등은 제외 (속도 향상 및 노이즈 제거)
                lower_src = src.lower()
                if any(x in lower_src for x in ['google', 'facebook', 'kakao', 'naver', 'analytics', 'ad', 'tracker', 'jquery']):
                    continue

                # 사이트 내부의 핵심 로직 파일(main, bundle, app 등)만 타겟팅
                # 또는 상대 경로로 시작하는 파일들
                if not (src.startswith('/') or './' in src or 'main' in lower_src or 'bundle' in lower_src or 'app' in lower_src or 'chunk' in lower_src):
                    continue

                js_url = urljoin(base_url, src)
                try:
                    # JS 파일 다운로드 (타임아웃 짧게)
                    js_resp = requests.get(js_url, headers=self.headers, timeout=5)
                    if js_resp.status_code == 200:
                        # JS 코드를 텍스트 더미로 간주하고 추가
                        js_text += " " + js_resp.text
                except:
                    continue
        except Exception:
            pass
        return js_text

    def normalize_phone(self, area, mid, end):
        """전화번호 포맷 통일"""
        # 대표번호인 경우 (mid가 없음)
        if mid is None:
            return f"{area}-{end}"
        return f"{area}-{mid}-{end}"

    def extract_links_from_soup(self, soup, info_dict):
        """HTML 태그(href)에서 전화번호/이메일 직접 추출"""
        if not soup: return

        # 1. tel: 링크 추출
        for a in soup.select('a[href^="tel:"]'):
            href = a.get('href', '')
            raw_num = href.replace('tel:', '').strip()
            clean_num = re.sub(r'[^0-9]', '', raw_num)
            
            # 대표번호 (8자리)
            if len(clean_num) == 8 and clean_num.startswith(('15', '16', '18')):
                fmt_num = f"{clean_num[:4]}-{clean_num[4:]}"
                info_dict['tel'].add(fmt_num)
            
            # 일반 번호 (9~11자리)
            elif len(clean_num) >= 9 and len(clean_num) <= 11:
                # 02-xxxx-xxxx
                if clean_num.startswith('02') and len(clean_num) >= 9:
                    fmt_num = f"{clean_num[:2]}-{clean_num[2:-4]}-{clean_num[-4:]}"
                    info_dict['tel'].add(fmt_num)
                # 031, 010, 070 등
                elif len(clean_num) >= 10:
                    prefix = clean_num[:3]
                    # [010 제한] tel 링크에서도 011~019는 제외
                    if prefix.startswith('01') and prefix != '010':
                        continue
                    
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

        try:
            text = text.encode('utf-8').decode('unicode_escape')
        except:
            pass
        
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

            if groups['intl_area']: # 패턴 A: 국제
                area, mid, end = groups['intl_area'], groups['intl_mid'], groups['intl_end']
                if not area.startswith('0'): area = '0' + area

            elif groups['rep_head']: # 패턴 B: 대표번호 (mid 없음)
                area, mid, end = groups['rep_head'], None, groups['rep_tail']

            elif groups['dom_area_sep']: # 패턴 C: 구분자 있음
                area, mid, end = groups['dom_area_sep'], groups['dom_mid_sep'], groups['dom_end_sep']

            elif groups['dom_area_raw']: # 패턴 D: 붙여씀
                area, mid, end = groups['dom_area_raw'], groups['dom_mid_raw'], groups['dom_end_raw']
            
            full_number = self.normalize_phone(area, mid, end)
            
            # 컨텍스트 기반 필터링
            start_pos = match.start()
            context_prev = text_lower[max(0, start_pos - 30):start_pos]
            context_next = text_lower[match.end():min(len(text_lower), match.end() + 10)]
            combined_context = context_prev + " " + context_next
            
            if any(k in combined_context for k in self.negative_keywords):
                continue

            if any(keyword in context_prev for keyword in self.fax_keywords):
                info_dict['fax'].add(full_number)
            else:
                info_dict['tel'].add(full_number)

    def extract_from_url(self, url):
        info = {'email': set(), 'tel': set(), 'fax': set()}
        
        if not url: return False, info
        if not url.startswith('http'): url = 'http://' + url

        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.encoding = resp.apparent_encoding 
            
            if resp.status_code != 200: return False, info

            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 1. 태그 추출
            self.extract_links_from_soup(soup, info)
            
            # 2. 텍스트 추출
            visible_text = soup.get_text(separator=' ', strip=True)
            frame_text = self.get_text_with_frames(soup, url)
            
            # JS 파일 내용을 가져오는 코드
            js_text = self.get_js_content(soup, url)
            
            raw_source_text = resp.text 

            # js_text를 검색 대상에 포함
            combined_text = f"{visible_text} {frame_text} {raw_source_text} {js_text}"
            
            self.extract_info_from_text(combined_text, info)
                    
            return True, info

        except Exception:
            return False, info

    def process_company(self, company_data):
        url = company_data.get('홈페이지', '')

        clean_url = str(url).strip().lower()
        is_invalid_url = (not url) or (url == "-") or (clean_url in ['http://', 'https://', ''])
        
        if is_invalid_url:
            return company_data

        success = False
        contact_info = {'email': set(), 'tel': set(), 'fax': set()}

        if url:
            success, contact_info = self.extract_from_url(url)

        existing_email = company_data.get('이메일', '')
        if existing_email: contact_info['email'].add(existing_email)
        if contact_info['email']:
            company_data['이메일'] = ", ".join(sorted(list(contact_info['email'])))[:300]

        existing_tel = company_data.get('전화번호', '')
        if existing_tel: contact_info['tel'].add(existing_tel)
        if contact_info['tel']:
            company_data['전화번호'] = ", ".join(sorted(list(contact_info['tel'])))[:100]

        existing_fax = company_data.get('팩스', '')
        if existing_fax: contact_info['fax'].add(existing_fax)
        if contact_info['fax']:
            company_data['팩스'] = ", ".join(sorted(list(contact_info['fax'])))[:100]

        return company_data

    def process_batch(self, data_list, max_workers=10):
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = list(executor.map(self.process_company, data_list))
        return results