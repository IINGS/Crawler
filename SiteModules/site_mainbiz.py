# SiteModules/site_mainbiz.py
import requests
from bs4 import BeautifulSoup
from crawler_base import BaseCrawler

class MainbizCrawler(BaseCrawler):
    def __init__(self):
        # 1. 부모 초기화 (그룹명: smes_gov, 출처명: 메인비즈)
        super().__init__("smes_gov", "메인비즈", checkpoint_key="smes_mainbiz")
        self.base_url = 'https://www.smes.go.kr/mainbiz/usr/innovation/list.do'

    def _get_text(self, td):
        """[Helper] 메인비즈 테이블 셀 내부 텍스트 추출"""
        span = td.select_one('.td_obj_text_value')
        return span.get_text(strip=True) if span else td.get_text(strip=True)

    def fetch_items(self, page):
        # 2. POST 요청 준비
        payload = {
            'pageNo': page, 
            'pageSize': 40,
            'cd_area': '', 'str_type': '', 'cd_searchType': '', 'str_searchKey': ''
        }

        try:
            # BaseCrawler의 헤더 생성 함수(_get_headers) 빌려 쓰기
            resp = requests.post(self.base_url, data=payload, headers=self._get_headers(), timeout=10)
            if resp.status_code != 200: return []

            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.select('table.list_board_table tbody tr')
            
            items = []
            for row in rows:
                cols = row.find_all('td')
                if len(cols) < 6: continue
                
                # 3. 데이터 추출 (딕셔너리 구성)
                items.append({
                    "기업명": self._get_text(cols[1]),
                    "대표자명": self._get_text(cols[3]),
                    "지역": self._get_text(cols[2]),
                    "업종": self._get_text(cols[5]),
                    "기술": self._get_text(cols[4]),
                    # 홈페이지를 비워두면 -> BaseCrawler의 SmartEngine이 자동으로 '구글 검색'을 수행함
                    "홈페이지": "" 
                })
            
            return items

        except Exception as e:
            self.log(f"Fetch Error: {e}")
            return []