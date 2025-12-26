# SiteModules/site_mainbiz.py
import requests
from bs4 import BeautifulSoup
import random
import time
import config
from crawler_core import DataProcessor
from state_manager import StateManager
from smart_extractor import SmartExtractor

class MainbizCrawler:
    def __init__(self):
        self.base_url = 'https://www.smes.go.kr/mainbiz/usr/innovation/list.do'
        self.processor = DataProcessor("메인비즈")
        self.group_name = "smes_gov"
        self.state = StateManager(self.group_name)
        self.smart_engine = SmartExtractor()

    def get_value(self, td):
        span = td.select_one('.td_obj_text_value')
        if span: return span.get_text(strip=True)
        return td.get_text(strip=True)

    def run(self):
        print(">>> [메인비즈] 수집 시작 (Deep Crawling Mode)")
        
        saved_page = self.state.load_checkpoint()
        start_page = saved_page if saved_page > 0 else 1
        
        if start_page > 1:
            print(f"  ▶ 지난번 작업 지점(Page {start_page})부터 이어합니다.")
        
        # 목표 페이지 (10페이지)
        end_page = 11

        for page in range(start_page, end_page):
            print(f"  - {page} 페이지 읽는 중...")
            
            try:
                payload = {
                    'pageNo': page,
                    'pageSize': 40,
                    'cd_area': '', 'str_type': '', 'cd_searchType': '', 'str_searchKey': ''
                }
                
                headers = {'User-Agent': random.choice(config.USER_AGENTS)}
                resp = requests.post(self.base_url, data=payload, headers=headers, timeout=10)
                
                if resp.status_code != 200:
                    print(f"    [접속 실패] {resp.status_code}")
                    continue

                soup = BeautifulSoup(resp.text, 'html.parser')
                rows = soup.select('table.list_board_table tbody tr') 

                batch_data = []
                skipped_count = 0

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 6: continue 
                    
                    raw_comp = self.get_value(cols[1])
                    raw_ceo = self.get_value(cols[3])
                    
                    extra_info = {
                        "지역": self.get_value(cols[2]),
                        "업종": self.get_value(cols[5]),
                        "기술": self.get_value(cols[4])
                        # 메인비즈 목록엔 홈페이지 주소가 없으므로 비워둠
                        # SmartExtractor가 자동으로 구글 검색을 시도함
                    }

                    record = self.processor.create_record(raw_comp, raw_ceo, extra_info)
                    
                    unique_key = record['고유키']
                    if self.state.is_new_or_changed(unique_key, record):
                        batch_data.append(record)
                    else:
                        skipped_count += 1

                if batch_data:
                    # [핵심 수정] 
                    # 메인비즈는 URL이 없어서 구글 검색을 동반하므로 시간이 좀 더 걸림
                    print(f"    -> [Deep Mining] {len(batch_data)}개 기업 외부 정밀 탐색 중 (구글 검색 포함)...")
                    enhanced_data = self.smart_engine.process_batch(batch_data, max_workers=10)

                    print(f"    -> GAS 전송 ({len(enhanced_data)}건) / 캐시 스킵 ({skipped_count}건)")
                    self.processor.send_to_gas(enhanced_data)
                else:
                    print(f"    -> 변경사항 없음. ({skipped_count}건 스킵)")

                self.state.save_checkpoint(page + 1)
                time.sleep(random.uniform(1, 3))

            except Exception as e:
                print(f"  [에러] {page}페이지: {e}")
                break
        
        if page == end_page - 1:
            print(">>> [메인비즈] 목표 달성. 체크포인트 초기화.")
            self.state.reset_checkpoint()
        else:
            print(">>> [메인비즈] 중단됨.")