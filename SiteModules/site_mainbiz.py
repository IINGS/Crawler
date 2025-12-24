# SiteModules/site_mainbiz.py
import requests
from bs4 import BeautifulSoup
import random
import time
import config
from crawler_core import DataProcessor

class MainbizCrawler:
    def __init__(self):
        # HTML 분석 결과 확인된 실제 URL
        self.base_url = 'https://www.smes.go.kr/mainbiz/usr/innovation/list.do'
        self.processor = DataProcessor("메인비즈")
        self.group_name = "smes_gov"

    def get_value(self, td):
        """반응형 테이블에서 실제 값만 추출하는 헬퍼 함수"""
        # td 안에 <span class="td_obj_text_value">값</span> 형태를 찾음
        span = td.select_one('.td_obj_text_value')
        if span:
            return span.get_text(strip=True)
        # 만약 없으면(PC버전 뷰 등) 그냥 텍스트 추출
        return td.get_text(strip=True)

    def run(self):
        print(">>> [메인비즈] 수집 시작")
        
        # 1~10페이지 수집 (필요시 조절)
        for page in range(1, 11):
            print(f"  - {page} 페이지 읽는 중...")
            
            try:
                # [분석 결과] pageNo 변수를 사용함
                payload = {
                    'pageNo': page,
                    'pageSize': 40,       # 기본값
                    'cd_area': '',        # 지역 전체
                    'str_type': '',       # 평가지표 전체
                    'cd_searchType': '',  # 검색조건 전체
                    'str_searchKey': ''   # 검색어 없음
                }
                
                headers = {'User-Agent': random.choice(config.USER_AGENTS)}
                
                resp = requests.post(self.base_url, data=payload, headers=headers, timeout=10)
                
                if resp.status_code != 200:
                    print(f"    [접속 실패] {resp.status_code}")
                    continue

                soup = BeautifulSoup(resp.text, 'html.parser')
                rows = soup.select('table.list_board_table tbody tr') 

                batch_data = []

                for row in rows:
                    cols = row.find_all('td')
                    
                    # 데이터가 없거나 형식이 다르면 스킵
                    if len(cols) < 6: continue 
                    
                    # HTML 구조에 맞춘 인덱스 매핑
                    # 0: 번호, 1: 업체명, 2: 지역, 3: 대표자명, 4: 평가업종, 5: 업종, 6: 만료일
                    
                    raw_comp = self.get_value(cols[1]) # 업체명
                    raw_ceo = self.get_value(cols[3])  # 대표자명
                    
                    # 자유 항목 (GAS 동적 컬럼용)
                    extra_info = {
                        "지역": self.get_value(cols[2]),
                        "업종": self.get_value(cols[5]),
                        "기술": self.get_value(cols[4])
                    }

                    record = self.processor.create_record(raw_comp, raw_ceo, extra_info)
                    batch_data.append(record)

                if batch_data:
                    res = self.processor.send_to_gas(batch_data)
                    if res and res.get('result') == 'success':
                        print(f"    -> 저장 성공 ({len(batch_data)}건)")
                        if res.get('cols_added'):
                             print(f"       [알림] 시트 헤더 추가됨: {res['cols_added']}")
                
                time.sleep(random.uniform(1, 3))

            except Exception as e:
                print(f"  [에러] {page}페이지: {e}")

        print(">>> [메인비즈] 수집 완료")
