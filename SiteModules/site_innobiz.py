# SiteModules/site_innobiz.py
import requests
from bs4 import BeautifulSoup, Comment
import random
import time
import config
from crawler_core import DataProcessor

class InnobizCrawler:
    def __init__(self):
        self.base_url = 'https://www.innobiz.net/company/company2_list.asp'
        self.processor = DataProcessor("이노비즈")
        self.group_name = "innobiz_net"

    def get_homepage_url(self, row):
        """이노비즈 특화: 주석(Comment) 안에 숨겨진 URL 추출"""
        homepage_url = ""
        comments = row.find_all(string=lambda text: isinstance(text, Comment))
        for c in comments:
            if "href" in c:
                soup = BeautifulSoup(c, 'html.parser')
                a_tag = soup.find('a')
                if a_tag and a_tag.get('href'):
                    homepage_url = a_tag.get('href')
                    if homepage_url.startswith("http://https://"):
                        homepage_url = homepage_url.replace("http://https://", "https://")
                    break
        return homepage_url

    def run(self):
        print(">>> [이노비즈] 수집 시작")
        
        # 1~20페이지 수집
        for page in range(1, 21):
            print(f"  - {page} 페이지 읽는 중...")
            
            try:
                params = {'Page': page} # GET 파라미터
                headers = {'User-Agent': random.choice(config.USER_AGENTS)}
                
                resp = requests.get(self.base_url, params=params, headers=headers, timeout=10)
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, 'html.parser')
                rows = soup.select('table.table_list_style1 tbody tr')

                batch_data = []

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 6: continue
                    if "없습니다" in row.get_text(): continue

                    # 1. 원본 데이터 추출
                    raw_comp = cols[1].get_text(strip=True)
                    raw_ceo = cols[2].get_text(strip=True)
                    
                    # 2. 추가 데이터(자유 항목) 딕셔너리 구성
                    # ※ 여기서 키 이름('지역', '업종' 등)이 시트의 헤더가 됩니다.
                    extra_info = {
                        "지역": cols[3].get_text(strip=True),
                        "기술": cols[4].get_text(strip=True),
                        "업종": cols[5].get_text(strip=True),
                        "홈페이지": self.get_homepage_url(row)
                    }

                    # 3. 엔진을 통해 전송용 데이터 생성 (정제 및 키 생성 자동화)
                    record = self.processor.create_record(raw_comp, raw_ceo, extra_info)
                    batch_data.append(record)

                # 페이지 단위 전송
                if batch_data:
                    res = self.processor.send_to_gas(batch_data)
                    if res and res.get('result') == 'success':
                        print(f"    -> 저장 성공 (신규: {res['inserted']}, 갱신: {res['updated']})")
                        if res.get('cols_added'):
                            print(f"    -> [알림] 새 항목 추가됨: {res['cols_added']}")
                
                time.sleep(random.uniform(1, 3)) # 차단 방지 대기

            except Exception as e:
                print(f"  [에러] {page}페이지: {e}")

        print(">>> [이노비즈] 수집 완료")
