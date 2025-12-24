# SiteModules/site_buykorea.py
import requests
from bs4 import BeautifulSoup
import random
import time
import config
from crawler_core import DataProcessor
from state_manager import StateManager 

class BuyKoreaCrawler:
    def __init__(self):
        self.base_url = 'https://buykorea.org/cp/cpy/ajax/selectCpComList.do'
        self.processor = DataProcessor("바이코리아")
        self.group_name = "buykorea_org"
        
        # [추가] 상태 관리자 장착
        self.state = StateManager(self.group_name)
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(config.USER_AGENTS),
            'Origin': 'https://buykorea.org',
            'Referer': 'https://buykorea.org/cp/cpy/selectCompaniesList.do',
            'X-Requested-With': 'XMLHttpRequest'
        })

    def get_detail_info(self, seller_id):
        """
        상세 페이지 정보 수집 함수
        - seller_id를 받아 상세 페이지에 접속합니다.
        - CEO, 주소, 홈페이지 등 주요 정보를 파싱합니다.
        - 실패 시 빈 딕셔너리와 빈 문자열을 반환하여 크롤러가 멈추지 않게 합니다.
        """
        detail_url = f"https://buykorea.org/seller-home/{seller_id}/com/index.do"
        try:
            time.sleep(random.uniform(0.5, 0.8)) 
            resp = self.session.get(detail_url, timeout=10)
            if resp.status_code != 200: return {}, ""

            soup = BeautifulSoup(resp.text, 'html.parser')
            info = {}
            ceo_name = ""

            items = soup.select('ul.shm-basic-box li')
            target_fields = {
                "CEO": "ceo", "Address": "addr", 
                "Homepage": "homepage", 
                "Main Markets": "주력시장", "Total Employees": "종업원수",
                "Year Established": "설립일", "Total Annual Revenue": "매출액",
                "Country / Region": "국가"
            }

            for item in items:
                label_tag = item.select_one('strong')
                if not label_tag: continue
                
                label_text = label_tag.get_text(strip=True)
                if label_text in target_fields:
                    key = target_fields[label_text]
                    value = ""
                    
                    a_tag = item.select_one('a')
                    p_tag = item.select_one('p')

                    if a_tag:
                        val_href = a_tag.get('href')
                        val_text = a_tag.get_text(strip=True)
                        value = val_href if val_href else val_text
                        if value and not value.startswith('http'): value = 'http://' + value
                    elif p_tag:
                        value = p_tag.get_text(strip=True)

                    if value and value != "-":
                        if key == "ceo": ceo_name = value
                        else: info[key] = value

            return info, ceo_name

        except Exception as e:
            return {}, ""

    def run(self):
        print(">>> [바이코리아] 수집 시작 (Smart Resume & Update Mode)")
        
        try:
            self.session.get('https://buykorea.org/cp/cpy/selectCompaniesList.do', timeout=10)
        except: pass

        # [핵심 1] 저장된 위치(Checkpoint)에서 시작
        current_skip = self.state.load_checkpoint()
        if current_skip > 0:
            print(f"  ▶ 지난번 작업 지점(Skip {current_skip})부터 이어합니다.")
        else:
            print("  ▶ 처음부터 시작합니다.")

        req_size = 100
        send_size = 10
        
        while True:
            # 멈춤 신호를 받으면 안전하게 종료하는 로직이 있으면 좋지만, 여기선 생략
            
            params = {
                'sortOrder': '2',
                'srchChar': '', 'ctgryCd': '', 'goodsCtgryClCd': '', 'srchStr': '',
                'srchSkip': str(current_skip), 
                'srchCnt': str(req_size)
            }
            
            try:
                if 'Content-Type' in self.session.headers: del self.session.headers['Content-Type']
                resp = self.session.post(self.base_url, params=params, timeout=15)
                if resp.status_code != 200: break

                try:
                    data = resp.json()
                    items = data.get('comList', [])
                except: break

                print(f"  - Skip {current_skip}: 목록 {len(items)}개 수신.")
                if not items:
                    print("    -> 수집 완료. 체크포인트를 초기화합니다.")
                    self.state.reset_checkpoint() # 다 끝났으니 다음번엔 0부터
                    break
                
                buffer_data = []
                skipped_count = 0 # 로컬 캐시 덕분에 건너뛴 개수

                for i, item in enumerate(items):
                    try:
                        raw_comp = item.get('engEntpName', '이름없음')
                        link = item.get('entpUrl', '')
                        seller_id = ""
                        # ID 추출 로직 (기존 동일)
                        if link:
                            parts = link.split('/')
                            for part in parts:
                                if part.isdigit(): seller_id = part; break
                            if not seller_id and len(parts) > 0: seller_id = parts[-1]

                        # [최적화 핵심] 상세 페이지 가기 전에 캐시 확인은 어려움 (상세 정보가 변했을 수 있으니)
                        # 하지만 '목록 상의 정보'만으로 거를 수 있다면 여기서 거르는 게 베스트.
                        # 여기서는 정확성을 위해 '상세 수집 후' 비교합니다.
                        
                        detail_info = {}
                        raw_ceo = ""
                        
                        if seller_id:
                            detail_info, raw_ceo = self.get_detail_info(seller_id)
                        if not raw_ceo: raw_ceo = "확인필요"

                        extra_info = {} 
                        extra_info.update(detail_info)

                        # 레코드 생성
                        record = self.processor.create_record(raw_comp, raw_ceo, extra_info)
                        unique_key = record['고유키'] # DataProcessor가 만들어준 키

                        # [핵심 2] 데이터 변경 확인
                        if self.state.is_new_or_changed(unique_key, record):
                            # 바뀐 게 있으면 버퍼에 추가 (GAS 전송 대기)
                            buffer_data.append(record)
                            print(f"\r    [{i+1}/{len(items)}] [NEW] {raw_comp[:10]}...", end="")
                        else:
                            # 바뀐 게 없으면 패스 (GAS 전송 안 함 -> 엄청 빠름)
                            skipped_count += 1
                            print(f"\r    [{i+1}/{len(items)}] [SKIP] {raw_comp[:10]}...", end="")

                        # 버퍼가 차면 전송
                        if len(buffer_data) >= send_size:
                            print(f"\n       >> GAS 전송 ({len(buffer_data)}건) / 캐시 스킵 ({skipped_count}건)")
                            self.processor.send_to_gas(buffer_data)
                            buffer_data = [] 

                    except Exception as inner_e:
                        continue

                # 잔여 데이터 전송
                if buffer_data:
                    print(f"\n       >> GAS 잔여 전송 ({len(buffer_data)}건)")
                    self.processor.send_to_gas(buffer_data)

                # [핵심 3] 한 페이지가 무사히 끝나면 체크포인트 저장
                # 다음 페이지 시작점 저장
                next_skip = current_skip + req_size
                self.state.save_checkpoint(next_skip)
                
                print(f"\n    -> 페이지 완료 (SKIP 누적: {skipped_count}건). 저장됨.")
                current_skip = next_skip
                time.sleep(random.uniform(2, 4))

            except Exception as e:
                print(f"  [에러] {e}")
                break

        print(">>> [바이코리아] 수집 완료")