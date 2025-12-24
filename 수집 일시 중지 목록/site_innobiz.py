# SiteModules/site_innobiz.py
import requests
from bs4 import BeautifulSoup, Comment
import random
import time
import config
from crawler_core import DataProcessor
# [추가] 상태 관리자
from state_manager import StateManager

class InnobizCrawler:
    def __init__(self):
        self.base_url = 'https://www.innobiz.net/company/company2_list.asp'
        self.processor = DataProcessor("이노비즈")
        self.group_name = "innobiz_net"
        # [추가] 상태 관리자 장착
        self.state = StateManager(self.group_name)

    def get_homepage_url(self, row):
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
        print(">>> [이노비즈] 수집 시작 (Smart Resume Mode)")
        
        # [핵심 1] 시작 페이지 로드
        saved_page = self.state.load_checkpoint()
        start_page = saved_page if saved_page > 0 else 1
        
        if start_page > 1:
            print(f"  ▶ 지난번 작업 지점(Page {start_page})부터 이어합니다.")

        # 목표 페이지 (기존 코드 20페이지)
        end_page = 21

        for page in range(start_page, end_page):
            print(f"  - {page} 페이지 읽는 중...")
            
            try:
                params = {'Page': page}
                headers = {'User-Agent': random.choice(config.USER_AGENTS)}
                
                resp = requests.get(self.base_url, params=params, headers=headers, timeout=10)
                if resp.status_code != 200: continue

                soup = BeautifulSoup(resp.text, 'html.parser')
                rows = soup.select('table.table_list_style1 tbody tr')

                batch_data = []
                skipped_count = 0

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 6: continue
                    if "없습니다" in row.get_text(): continue

                    raw_comp = cols[1].get_text(strip=True)
                    raw_ceo = cols[2].get_text(strip=True)
                    
                    extra_info = {
                        "지역": cols[3].get_text(strip=True),
                        "기술": cols[4].get_text(strip=True),
                        "업종": cols[5].get_text(strip=True),
                        "홈페이지": self.get_homepage_url(row)
                    }

                    record = self.processor.create_record(raw_comp, raw_ceo, extra_info)
                    
                    # [핵심 2] 변경 감지
                    unique_key = record['고유키']
                    if self.state.is_new_or_changed(unique_key, record):
                        batch_data.append(record)
                    else:
                        skipped_count += 1

                # [핵심 3] 변경분만 전송
                if batch_data:
                    print(f"    -> GAS 전송 ({len(batch_data)}건) / 캐시 스킵 ({skipped_count}건)")
                    self.processor.send_to_gas(batch_data)
                else:
                    print(f"    -> 변경사항 없음. ({skipped_count}건 스킵)")
                
                # [핵심 4] 페이지 완료 시 체크포인트 저장
                self.state.save_checkpoint(page + 1)

                time.sleep(random.uniform(1, 3))

            except Exception as e:
                print(f"  [에러] {page}페이지: {e}")
                break

        # 완료 처리
        if page == end_page - 1:
            print(">>> [이노비즈] 목표 달성. 체크포인트 초기화.")
            self.state.reset_checkpoint()
        else:
            print(">>> [이노비즈] 중단됨. 다음 실행 시 이어서 진행합니다.")