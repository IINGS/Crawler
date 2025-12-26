# SiteModules/site_buykorea.py
import requests
from bs4 import BeautifulSoup
import random
import time
import config
from concurrent.futures import ThreadPoolExecutor # [추가] 병렬 처리를 위한 모듈
from crawler_core import DataProcessor
from state_manager import StateManager 
from smart_extractor import SmartExtractor

class BuyKoreaCrawler:
    def __init__(self):
        self.base_url = 'https://buykorea.org/cp/cpy/ajax/selectCpComList.do'
        self.processor = DataProcessor("바이코리아")
        self.group_name = "buykorea_org"
        
        self.state = StateManager(self.group_name)
        self.smart_engine = SmartExtractor()
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(config.USER_AGENTS),
            'Origin': 'https://buykorea.org',
            'Referer': 'https://buykorea.org/cp/cpy/selectCompaniesList.do',
            'X-Requested-With': 'XMLHttpRequest'
        })

    def get_detail_info(self, seller_id):
        """상세 페이지 정보 수집 (주소 제외)"""
        detail_url = f"https://buykorea.org/seller-home/{seller_id}/com/index.do"
        try:
            # 병렬 실행 시 너무 빠르면 차단될 수 있으므로 약간의 텀 유지
            time.sleep(random.uniform(0.5, 1.0)) 
            resp = self.session.get(detail_url, timeout=10)
            if resp.status_code != 200: return {}, ""

            soup = BeautifulSoup(resp.text, 'html.parser')
            info = {}
            ceo_name = ""

            items = soup.select('ul.shm-basic-box li')
            
            target_fields = {
                "CEO": "ceo", 
                # "Address": "addr", (수집 제외)
                "Homepage": "homepage", 
                "Main Markets": "주력시장", 
                "Total Employees": "종업원수",
                "Total Annual Revenue": "매출액"
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

        except Exception:
            return {}, ""

    def _process_item(self, item):
        """[신규] 개별 기업 정보를 병렬로 처리하기 위한 단위 함수"""
        try:
            raw_comp = item.get('engEntpName', '이름없음')
            link = item.get('entpUrl', '')
            
            seller_id = ""
            if link:
                parts = link.split('/')
                for part in parts:
                    if part.isdigit():
                        seller_id = part
                        break
                if not seller_id and len(parts) > 0: seller_id = parts[-1]

            detail_info = {}
            raw_ceo = ""
            
            # 상세 페이지 접속 (여기가 병렬로 실행됨)
            if seller_id:
                detail_info, raw_ceo = self.get_detail_info(seller_id)
            
            if not raw_ceo: raw_ceo = "확인필요"

            extra_info = {} 
            extra_info.update(detail_info)

            record = self.processor.create_record(raw_comp, raw_ceo, extra_info)
            unique_key = record['고유키']

            # 변경 감지
            if self.state.is_new_or_changed(unique_key, record):
                return record # 유효 데이터
            else:
                return "SKIPPED" # 스킵 신호

        except Exception as e:
            return None

    def run(self):
        print(">>> [바이코리아] 수집 시작 (High Performance Mode)")
        
        try:
            self.session.get('https://buykorea.org/cp/cpy/selectCompaniesList.do', timeout=10)
        except: pass

        current_skip = self.state.load_checkpoint()
        if current_skip > 0:
            print(f"  ▶ 지난번 작업 지점(Skip {current_skip})부터 이어합니다.")

        req_size = 100
        # [최적화 1] 한 번에 모아서 보내는 양을 늘림 (GAS 통신 횟수 감소)
        send_size = 50 
        
        # [최적화 2] 바이코리아 내부 페이지 동시 접속 수 (너무 높으면 429 차단)
        # 10~15 정도가 안전하면서도 충분히 빠릅니다.
        MAX_INTERNAL_WORKERS = 12 

        while True:
            params = {
                'sortOrder': '2',
                'srchChar': '', 'ctgryCd': '', 'goodsCtgryClCd': '', 'srchStr': '',
                'srchSkip': str(current_skip), 
                'srchCnt': str(req_size)
            }
            
            try:
                if 'Content-Type' in self.session.headers: del self.session.headers['Content-Type']
                resp = self.session.post(self.base_url, params=params, timeout=15)
                
                if resp.status_code != 200:
                    print(f"    [접속 실패] {resp.status_code}")
                    break

                try:
                    data = resp.json()
                    items = data.get('comList', [])
                except Exception:
                    break

                print(f"  - Skip {current_skip}: 목록 {len(items)}개 수신. 병렬 상세 수집 시작...")

                if not items:
                    print("    -> 더 이상 데이터가 없습니다. 수집 완료.")
                    self.state.reset_checkpoint()
                    break
                
                buffer_data = []
                skipped_count = 0

                # [최적화 3] 목록에 있는 100개를 병렬로 한꺼번에 상세 정보 긁어오기
                with ThreadPoolExecutor(max_workers=MAX_INTERNAL_WORKERS) as executor:
                    # _process_item 함수를 병렬 실행
                    results = list(executor.map(self._process_item, items))

                # 결과 분류 (유효 데이터 vs 스킵 데이터)
                for res in results:
                    if res == "SKIPPED":
                        skipped_count += 1
                    elif res and isinstance(res, dict):
                        buffer_data.append(res)

                # 버퍼 처리 (Deep Mining -> GAS 전송)
                # buffer_data가 많을 수 있으므로 send_size 단위로 쪼개서 처리
                for i in range(0, len(buffer_data), send_size):
                    batch = buffer_data[i:i + send_size]
                    
                    print(f"\n       >> [Deep Mining] {len(batch)}개 기업 외부 정밀 탐색 중...")
                    # SmartExtractor는 외부 사이트이므로 워커 수를 좀 더 높게(20) 써도 됨
                    enhanced_data = self.smart_engine.process_batch(batch, max_workers=20)
                    
                    print(f"       >> GAS 전송 ({len(enhanced_data)}건) / 누적 스킵 ({skipped_count}건)")
                    self.processor.send_to_gas(enhanced_data)

                # 체크포인트 저장
                next_skip = current_skip + req_size
                self.state.save_checkpoint(next_skip)
                
                print(f"    -> 페이지 완료. (처리: {len(buffer_data)}, 스킵: {skipped_count}). 저장됨.")
                current_skip = next_skip
                
                # 페이지 넘길 때는 조금 쉬어주기
                time.sleep(random.uniform(1.5, 3.0))

            except Exception as e:
                print(f"  [에러] Skip {current_skip}: {e}")
                time.sleep(5) # 에러 시 잠시 대기
                # break 하지 않고 재시도하거나 다음 루프로 (상황에 따라 결정)
                break

        print(">>> [바이코리아] 수집 완료")