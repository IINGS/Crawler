# SiteModules/site_mainbiz.py
import requests
from bs4 import BeautifulSoup
import random
import time
import config
from crawler_core import DataProcessor
# [추가] 상태 관리자
from state_manager import StateManager

class MainbizCrawler:
    def __init__(self):
        self.base_url = 'https://www.smes.go.kr/mainbiz/usr/innovation/list.do'
        self.processor = DataProcessor("메인비즈")
        self.group_name = "smes_gov"
        # [추가] 상태 관리자 장착
        self.state = StateManager(self.group_name)

    def get_value(self, td):
        span = td.select_one('.td_obj_text_value')
        if span: return span.get_text(strip=True)
        return td.get_text(strip=True)

    def run(self):
        print(">>> [메인비즈] 수집 시작 (Smart Resume Mode)")
        
        # [핵심 1] 저장된 페이지부터 시작 (없으면 1페이지)
        saved_page = self.state.load_checkpoint()
        start_page = saved_page if saved_page > 0 else 1
        
        if start_page > 1:
            print(f"  ▶ 지난번 작업 지점(Page {start_page})부터 이어합니다.")
        
        # 목표 페이지 (기존 코드의 10페이지 제한 유지)
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
                skipped_count = 0 # 스킵 카운터

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 6: continue 
                    
                    raw_comp = self.get_value(cols[1])
                    raw_ceo = self.get_value(cols[3])
                    
                    extra_info = {
                        "지역": self.get_value(cols[2]),
                        "업종": self.get_value(cols[5]),
                        "기술": self.get_value(cols[4])
                    }

                    record = self.processor.create_record(raw_comp, raw_ceo, extra_info)
                    
                    # [핵심 2] 데이터 변경 확인 (DB 비교)
                    unique_key = record['고유키']
                    if self.state.is_new_or_changed(unique_key, record):
                        batch_data.append(record) # 변경됨 -> 전송 목록에 추가
                        # print(f"\r    [NEW] {raw_comp}...", end="") # 너무 시끄러우면 주석 처리
                    else:
                        skipped_count += 1
                        # print(f"\r    [SKIP] {raw_comp}...", end="")

                # [핵심 3] 변경된 데이터만 GAS 전송
                if batch_data:
                    print(f"    -> GAS 전송 ({len(batch_data)}건) / 캐시 스킵 ({skipped_count}건)")
                    self.processor.send_to_gas(batch_data)
                else:
                    print(f"    -> 변경사항 없음. ({skipped_count}건 스킵)")

                # [핵심 4] 한 페이지 성공 시 체크포인트 저장 (다음 페이지 번호)
                self.state.save_checkpoint(page + 1)
                
                time.sleep(random.uniform(1, 3))

            except Exception as e:
                print(f"  [에러] {page}페이지: {e}")
                # 에러 나면 멈춤 (다음 실행 시 이 페이지부터 다시 함)
                break
        
        # 루프가 정상적으로 끝났다면 (목표 페이지 도달)
        if page == end_page - 1:
            print(">>> [메인비즈] 목표 달성. 체크포인트 초기화.")
            self.state.reset_checkpoint()
        else:
            print(">>> [메인비즈] 중단됨. 다음 실행 시 이어서 진행합니다.")