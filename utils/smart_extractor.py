# smart_extractor.py
import re
import aiohttp
import concurrent.futures
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin

class SmartExtractor:
    def __init__(self, session=None):
        self.session = session
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        }
        
        self.email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        
        # 존재하는 국번만 허용 (Whitelist)
        # 잘못된 국번(045, 069, 023 등)이 들어오는 것을 방지
        # 02: 서울
        # 031~033: 경기/인천/강원
        # 041~044: 충청/대전/세종 (045, 048 등 제외됨)
        # 051~055: 경상/부산/대구/울산
        # 061~064: 전라/광주/제주 (069 제외됨)
        # 010: 휴대폰 (011~019 제외)
        # 070: 인터넷전화, 050: 안심번호, 080: 수신자부담, 060: 정보제공
        self.area_code_pattern = r"(?:02|03[1-3]|04[1-4]|05[1-5]|06[1-4]|010|070|080|050\d|060)"

        self.phone_regex = re.compile(r"""
            (?<!\d)
            (?:
                # 패턴 A: 국제전화 (+82)
                (?:\+|00)82[\s\.\-]*\(?0?\)?[\s\.\-]*
                (?P<intl_area>\d{2,3})
                [\s\.\-\)]*
                (?P<intl_mid>\d{3,4})
                [\s\.\-]*
                (?P<intl_end>\d{4})
                |
                # 패턴 B: 전국 대표번호 (15xx, 16xx, 18xx)
                (?P<rep_head>(?:15|16|18)\d{2})
                [\s\.\-]*
                (?P<rep_tail>\d{4})
                |
                # 패턴 C: 국내전화 (구분자)
                (?P<dom_area_sep>""" + self.area_code_pattern + r""")
                [\s\.\-\)]+
                (?P<dom_mid_sep>\d{3,4})
                [\s\.\-]+
                (?P<dom_end_sep>\d{4})
                |
                # 패턴 D: 국내전화 (붙여씀)
                (?P<dom_area_raw>""" + self.area_code_pattern + r""")
                (?P<dom_mid_raw>\d{3,4})
                (?P<dom_end_raw>\d{4})
            )
            (?!\d)
        """, re.VERBOSE)
        
        self.fax_keywords = ['fax', 'facsimile', 'f.', 'f:', 'fx', '팩스']
        
        # 부정 키워드 (은행/계좌번호 등 오탐지 방지)
        self.negative_keywords = [
            '계좌', '은행', '예금', 'bank', 'account', 'iban', 'swift', '예금주',
            'price'
        ]
        
        # 쓰레기 번호 목록
        # 웹사이트 템플릿에 자주 쓰이는 가짜 번호들
        self.garbage_full_numbers = [
            '02-1212-2121', '02-1231-2132', '010-101-0101', '010-0000-0000', 
            '02-000-0000', '02-1111-1111', '010-1234-5678', '010-1111-2222',
            '000-0000-0000', '123-456-7890', '070-1234-5678'
        ]

        self.blocked_domains = [
            'facebook.com', 'instagram.com', 'jobkorea.co.kr', 'saramin.co.kr', 
            'jobplanet.co.kr', 'buykorea.org', 'incruit.com', 'catch.co.kr', 
            'work.go.kr', 'linkedin.com', 'youtube.com', 'namu.wiki', 'nicebiz', 'kedkorea',
            'crediv.co.kr', 'kisreport.com', 'blog.naver.com'
        ]

    def is_garbage_number(self, mid, end, full_formatted):
        if not mid or not end: return True
        
        # 1. 완전 일치 블랙리스트 확인
        if full_formatted in self.garbage_full_numbers:
            return True

        # 2. 단순 연속/반복 숫자 패턴
        garbage_patterns = ['0000', '1111', '2222', '3333', '4444', '5555', '6666', '7777', '8888', '9999', '1234', '2345', '5678', '4321']
        
        if mid in garbage_patterns or end in garbage_patterns:
            return True
            
        # 3. 국번과 뒷자리가 똑같은 경우 (예: 1234-1234)
        if mid == end:
            return True
            
        # 4. 너무 짧은 번호 (오탐지 방지)
        if len(mid) < 3 or len(end) < 4:
            return True

        return False

    async def _fetch_text(self, url, session):
        """내부 헬퍼: URL에서 텍스트만 안전하게 가져옴"""
        try:
            async with session.get(url, headers=self.headers, timeout=5) as resp:
                if resp.status == 200:
                    return await resp.text()
        except:
            pass
        return ""

    async def get_text_with_frames(self, soup, base_url, session):
        text_content = ""
        try:
            frames = soup.select('frame, iframe')
            if not frames: return ""
            
            for frame in frames:
                src = frame.get('src')
                if not src: continue
                frame_url = urljoin(base_url, src)
                
                html = await self._fetch_text(frame_url, session)
                if html:
                    frame_soup = BeautifulSoup(html, 'html.parser')
                    text_content += " " + frame_soup.get_text(separator=' ', strip=True)
        except: pass
        return text_content
    
    async def get_js_content(self, soup, base_url, session):
        js_text = ""
        try:
            scripts = soup.select('script[src]')
            for script in scripts:
                src = script.get('src')
                if not src: continue
                
                lower_src = src.lower()
                if any(x in lower_src for x in ['google', 'facebook', 'kakao', 'naver', 'analytics', 'ad', 'tracker', 'jquery', 'bootstrap', 'swiper', 'slick', 'aos', 'gsap']):
                    continue

                if not (src.startswith('/') or './' in src or 'main' in lower_src or 'bundle' in lower_src or 'app' in lower_src or 'chunk' in lower_src):
                    continue

                js_url = urljoin(base_url, src)
                
                content = await self._fetch_text(js_url, session)
                if content:
                    js_text += " " + content
        except:
            pass
        return js_text

    def normalize_phone(self, area, mid, end):
        if mid is None:
            return f"{area}-{end}"
        return f"{area}-{mid}-{end}"

    def extract_links_from_soup(self, soup, info_dict):
        if not soup: return

        for a in soup.select('a[href^="tel:"]'):
            href = a.get('href', '')
            raw_num = href.replace('tel:', '').strip()
            clean_num = re.sub(r'[^0-9]', '', raw_num)
            
            # 대표번호 (15xx-xxxx)
            if len(clean_num) == 8 and clean_num.startswith(('15', '16', '18')):
                fmt_num = f"{clean_num[:4]}-{clean_num[4:]}"
                info_dict['tel'].add(fmt_num)
            
            # 일반 번호 (9~11자리)
            elif len(clean_num) >= 9 and len(clean_num) <= 11:
                # 02-xxxx-xxxx
                if clean_num.startswith('02') and len(clean_num) >= 9:
                    mid_part = clean_num[2:-4]
                    end_part = clean_num[-4:]
                    full_fmt = f"02-{mid_part}-{end_part}"
                    
                    if not self.is_garbage_number(mid_part, end_part, full_fmt):
                        info_dict['tel'].add(full_fmt)

                # 031, 010, 070 등
                elif len(clean_num) >= 10:
                    prefix = clean_num[:3]
                    # [010 제한] tel 링크에서도 011~019는 제외
                    if prefix.startswith('01') and prefix != '010':
                        continue
                    
                    mid_part = clean_num[3:-4]
                    end_part = clean_num[-4:]
                    full_fmt = f"{prefix}-{mid_part}-{end_part}"
                    
                    if not self.is_garbage_number(mid_part, end_part, full_fmt):
                        info_dict['tel'].add(full_fmt)

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
        
        emails = self.email_pattern.findall(text)
        for email in emails:
            if not any(ext in email.lower() for ext in ['.png', '.jpg', '.gif', '.js', 'w3.org', 'example', 'sentry', 'u003e', '.css', 'node_modules']):
                info_dict['email'].add(email)

        matches = self.phone_regex.finditer(text_lower)
        for match in matches:
            groups = match.groupdict()
            
            area, mid, end = "", "", ""

            if groups['intl_area']:
                area, mid, end = groups['intl_area'], groups['intl_mid'], groups['intl_end']
                if not area.startswith('0'): area = '0' + area
            elif groups['rep_head']:
                area, mid, end = groups['rep_head'], None, groups['rep_tail']
            elif groups['dom_area_sep']:
                area, mid, end = groups['dom_area_sep'], groups['dom_mid_sep'], groups['dom_end_sep']
            elif groups['dom_area_raw']:
                area, mid, end = groups['dom_area_raw'], groups['dom_mid_raw'], groups['dom_end_raw']
            
            full_number = self.normalize_phone(area, mid, end)

            # 가짜 번호 판별 시 full_number도 함께 전달
            if self.is_garbage_number(mid, end, full_number):
                continue

            start_pos = match.start()
            context_prev = text_lower[max(0, start_pos - 20):start_pos]
            context_next = text_lower[match.end():min(len(text_lower), match.end() + 10)]
            combined_context = context_prev + " " + context_next
            
            if any(k in combined_context for k in self.negative_keywords):
                continue

            if any(keyword in context_prev for keyword in self.fax_keywords):
                info_dict['fax'].add(full_number)
            else:
                info_dict['tel'].add(full_number)

    async def extract_from_url(self, url):
        info = {'email': set(), 'tel': set(), 'fax': set()}
        
        if not url: return False, info
        if not url.startswith('http'): url = 'http://' + url

        should_close_session = False
        session = self.session
        if session is None:
            session = aiohttp.ClientSession()
            should_close_session = True

        try:
            async with session.get(url, headers=self.headers, timeout=10) as resp:
                if resp.status != 200: 
                    return False, info

                raw_source_text = await resp.text()

                soup = BeautifulSoup(raw_source_text, 'html.parser')
                
                self.extract_links_from_soup(soup, info)
                
                visible_text = soup.get_text(separator=' ', strip=True)
                
                frame_text = await self.get_text_with_frames(soup, url, session)
                js_text = await self.get_js_content(soup, url, session) 
                
                combined_text = f"{visible_text} {frame_text} {raw_source_text} {js_text}"
                
                self.extract_info_from_text(combined_text, info)
                        
            return True, info

        except Exception:
            return False, info
        finally:
            if should_close_session:
                await session.close()

    async def process_company(self, company_data):
        url = company_data.get('홈페이지', '')

        clean_url = str(url).strip().lower()
        is_invalid_url = (not url) or (url == "-") or (clean_url in ['http://', 'https://', ''])
        
        if is_invalid_url:
             return company_data

        success = False
        contact_info = {'email': set(), 'tel': set(), 'fax': set()}

        if url:
            success, contact_info = await self.extract_from_url(url)

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
    
    def extract_contacts(self, text):
        """
        GenericAsyncCrawler 엔진과의 호환성을 위한 래퍼 메서드
        텍스트 덩어리를 받아 이메일/전화번호/팩스를 추출하여 딕셔너리로 반환
        """
        info = {'email': set(), 'tel': set(), 'fax': set()}
        
        # 기존 로직 재사용
        self.extract_info_from_text(text, info)
        
        # 세트(Set)를 문자열로 변환하여 반환
        return {
            "이메일": ", ".join(sorted(list(info['email']))),
            "전화번호": ", ".join(sorted(list(info['tel']))),
            "팩스": ", ".join(sorted(list(info['fax'])))
        }