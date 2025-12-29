# SiteModules/site_buykorea.py
import requests
from bs4 import BeautifulSoup
from crawler_base import BaseCrawler

class BuyKoreaCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("buykorea_org", "바이코리아")
        self.base_url = 'https://buykorea.org/cp/cpy/ajax/selectCpComList.do'
        self.session = requests.Session() # 세션 유지 필수
        self.req_size = 100
        # 파싱할 필드 매핑 (사이트 항목명: 저장할 키값)
        self.field_map = {
            "CEO": "대표자명", "Homepage": "홈페이지", "Main Markets": "주력시장",
            "Total Employees": "종업원수", "Total Annual Revenue": "매출액"
        }

    def _get_detail_info(self, item):
        """[Worker] 상세 페이지 파싱 (압축 로직)"""
        try:
            # 1. Seller ID 추출 (한 줄로 단축)
            link = item.get('entpUrl', '')
            seller_id = next((p for p in link.split('/') if p.isdigit()), None)
            if not seller_id: return None

            # 2. 접속 및 파싱
            url = f"https://buykorea.org/seller-home/{seller_id}/com/index.do"
            resp = self.session.get(url, timeout=10)
            if resp.status_code != 200: return None
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            info = {"기업명": item.get('engEntpName', ''), "대표자명": ""}

            # 3. 데이터 추출 (Loop 압축)
            # ul.shm-basic-box li 태그 안의 strong(라벨)과 내용(a 또는 p)을 찾음
            for li in soup.select('ul.shm-basic-box li'):
                label = li.select_one('strong')
                key = self.field_map.get(label.get_text(strip=True)) if label else None
                if not key: continue

                # 내용 추출: a태그의 href가 있으면 그거 쓰고, 없으면 텍스트 사용
                val_tag = li.select_one('a, p')
                if not val_tag: continue
                
                val = val_tag.get('href') if val_tag.name == 'a' and val_tag.get('href') else val_tag.get_text(strip=True)
                
                # http 프로토콜 보정 및 저장
                if val and val != "-":
                    if key == "홈페이지" and not val.startswith(('http', 'javascript')): val = 'http://' + val
                    info[key] = val

            return info
        except: return None

    def fetch_items(self, page):
        # 1. 목록 요청 (간소화)
        params = {'srchSkip': str((page - 1) * self.req_size), 'srchCnt': str(self.req_size), 'sortOrder': '2'}
        data = self.post_json(self.base_url, params=params)
        items = data.get('comList', []) if data else []
        
        if not items: return []
        
        self.log(f"목록 {len(items)}개 확보. 병렬 상세 수집 시작...")
        
        # 2. 병렬 처리 (BaseCrawler 기능 활용)
        return self.fetch_parallel(items, self._get_detail_info, max_workers=12)