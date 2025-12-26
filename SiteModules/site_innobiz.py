# SiteModules/site_innobiz.py
import requests
from bs4 import BeautifulSoup, Comment
import random
import time
import config
from crawler_core import DataProcessor
from state_manager import StateManager
from smart_extractor import SmartExtractor

class InnobizCrawler:
    def __init__(self):
        self.base_url = 'https://www.innobiz.net/company/company2_list.asp'
        self.processor = DataProcessor("이노비즈")
        self.group_name = "innobiz_net"
        self.state = StateManager(self.group_name)
        self.smart_engine = SmartExtractor()

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
        print(">>> [이노비즈] 수집 시작 (끝까지 달리는 모드)")
        
        saved_page = self.state.load_checkpoint()
        # 저장된 페이지가 있으면 거기서부터, 없으면 1페이지부터
        current_page = saved_page if saved_page > 0 else 1
        
        if current_page > 1:
            print(f"  ▶ 지난번 작업 지점(Page {current_page})부터 이어합니다.")

        # [수정] for 루프 대신 while True를 사용하여 끝까지 반복
        while True:
            print(f"  - {current_page} 페이지 읽는 중...")
            
            try:
                params = {'Page': current_page}
                headers = {'User-Agent': random.choice(config.USER_AGENTS)}
                
                resp = requests.get(self.base_url, params=params, headers=headers, timeout=10)
                if resp.status_code != 200: 
                    print(f"    [접속 실패] 상태코드 {resp.status_code}")
                    time.sleep(5)
                    continue

                soup = BeautifulSoup(resp.text, 'html.parser')
                rows = soup.select('table.table_list_style1 tbody tr')

                # [종료 조건 1] 행이 아예 없으면 종료
                if not rows:
                    print(">>> [이노비즈] 더 이상 데이터가 없습니다. 수집을 종료합니다.")
                    break

                # [종료 조건 2] "검색된 결과가 없습니다" 메시지가 있는 경우 종료
                if len(rows) == 1 and "없습니다" in rows[0].get_text():
                    print(">>> [이노비즈] 마지막 페이지에 도달했습니다. 수집을 종료합니다.")
                    break

                batch_data = []
                skipped_count = 0

                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) < 6: continue
                    # 행 안에 "없습니다" 텍스트가 있으면 건너뜀 (방어 코드)
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
                    
                    unique_key = record['고유키']
                    if self.state.is_new_or_changed(unique_key, record):
                        batch_data.append(record)
                    else:
                        skipped_count += 1

                # 변경 데이터 처리
                if batch_data:
                    print(f"    -> [Deep Mining] {len(batch_data)}개 기업 홈페이지 탐색 중...")
                    enhanced_data = self.smart_engine.process_batch(batch_data, max_workers=10)
                    
                    print(f"    -> GAS 전송 ({len(enhanced_data)}건) / 캐시 스킵 ({skipped_count}건)")
                    self.processor.send_to_gas(enhanced_data)
                else:
                    print(f"    -> 변경사항 없음. ({skipped_count}건 스킵)")
                
                # 페이지 완료 후 저장 및 페이지 번호 증가
                # 다음 시작할 페이지는 current_page + 1
                self.state.save_checkpoint(current_page + 1)
                current_page += 1

                time.sleep(random.uniform(1, 3))

            except Exception as e:
                print(f"  [에러] {current_page}페이지: {e}")
                # 에러 발생 시 반복 중단 (다음 실행 시 저장된 페이지부터 다시 시작)
                break

        # 루프가 정상적으로 break 되어 끝난 경우 (수집 완료)
        print(">>> [이노비즈] 모든 수집이 완료되었습니다. 체크포인트 초기화.")
        self.state.reset_checkpoint()