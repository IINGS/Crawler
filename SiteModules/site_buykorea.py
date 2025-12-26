# SiteModules/site_buykorea.py
import requests
from bs4 import BeautifulSoup
import random
import time
import config
from crawler_core import DataProcessor
from state_manager import StateManager 
from smart_extractor import SmartExtractor  # [추가] 스마트 추출기

class BuyKoreaCrawler:
    def __init__(self):
        self.base_url = 'https://buykorea.org/cp/cpy/ajax/selectCpComList.do'
        self.processor = DataProcessor("바이코리아")
        self.group_name = "buykorea_org"
        
        # [핵심] 상태 관리자 & 스마트 엔진 장착
        self.state = StateManager(self.group_name)
        self.smart_engine = SmartExtractor()
        
        # 세션 설정
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': random.choice(config.USER_AGENTS),
            'Origin': 'https://buykorea.org',
            'Referer': 'https://buykorea.org/cp/cpy/selectCompaniesList.do',
            'X-Requested-With': 'XMLHttpRequest'
        })

    def get_detail_info(self, seller_id):
        """상세 페이지(내부) 정보 수집"""
        detail_url = f"https://buykorea.org/seller-home/{seller_id}/com/index.do"
        try:
            time.sleep(random.uniform(0.3, 0.6))
            resp = self.session.get(detail_url, timeout=10)
            if resp.status_code != 200: return {}, ""

            soup = BeautifulSoup(resp.text, 'html.parser')
            info = {}
            ceo_name = ""

            items = soup.select('ul.shm-basic-box li')
            target_fields = {
                "CEO": "ceo", 
                "Address": "addr", 
                "Homepage": "homepage", 
                "Main Markets": "주력시장", 
                "Total Employees": "종업원수",
                "Total Annual Revenue": "매출액"
                # "Year Established": "설립일",
                # "Country / Region": "국가"
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

    def run(self):
        print(">>> [바이코리아] 수집 시작 (Smart Deep Mining Mode)")
        
        # 세션 워밍업
        try:
            self.session.get('https://buykorea.org/cp/cpy/selectCompaniesList.do', timeout=10)
        except: pass

        # 1. 이어하기 지점 로드
        current_skip = self.state.load_checkpoint()
        if current_skip > 0:
            print(f"  ▶ 지난번 작업 지점(Skip {current_skip})부터 이어합니다.")

        req_size = 100
        send_size = 10
        
        while True:
            params = {
                'sortOrder': '2',        # Popularity
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

                print(f"  - Skip {current_skip}: 목록 {len(items)}개 수신.")

                if not items:
                    print("    -> 더 이상 데이터가 없습니다. 수집 완료.")
                    self.state.reset_checkpoint()
                    break
                
                buffer_data = []
                skipped_count = 0

                for i, item in enumerate(items):
                    try:
                        # 2. 기본 정보 파싱
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
                        
                        # 상세 페이지(내부) 수집
                        if seller_id:
                            detail_info, raw_ceo = self.get_detail_info(seller_id)
                        
                        if not raw_ceo: raw_ceo = "확인필요"

                        extra_info = {} 
                        extra_info.update(detail_info)

                        record = self.processor.create_record(raw_comp, raw_ceo, extra_info)
                        unique_key = record['고유키']

                        # 3. 변경 감지 (로컬 DB 체크)
                        if self.state.is_new_or_changed(unique_key, record):
                            buffer_data.append(record) # 변경됨 -> 버퍼에 추가
                        else:
                            skipped_count += 1 # 변경없음 -> 스킵

                        # 4. 버퍼가 차면 -> [심층 채굴] -> 전송
                        if len(buffer_data) >= send_size:
                            print(f"\n       >> [Deep Mining] {len(buffer_data)}개 기업 외부 정밀 탐색 중...")
                            
                            # ★ 병렬로 외부 사이트 접속 (이메일, 팩스, 구글링)
                            enhanced_data = self.smart_engine.process_batch(buffer_data, max_workers=10)
                            
                            print(f"       >> GAS 전송 ({len(enhanced_data)}건) / 캐시 스킵 누적 ({skipped_count}건)")
                            self.processor.send_to_gas(enhanced_data)
                            buffer_data = [] 

                    except Exception:
                        continue

                # 페이지 끝난 후 잔여 데이터 처리
                if buffer_data:
                    print(f"\n       >> [Deep Mining] 잔여 {len(buffer_data)}개 정밀 탐색 중...")
                    enhanced_data = self.smart_engine.process_batch(buffer_data, max_workers=10)
                    print(f"       >> GAS 잔여 전송 ({len(enhanced_data)}건)")
                    self.processor.send_to_gas(enhanced_data)

                # 5. 체크포인트 저장
                next_skip = current_skip + req_size
                self.state.save_checkpoint(next_skip)
                
                print(f"    -> 페이지 완료. (누적 스킵: {skipped_count}건). 저장됨.")
                current_skip = next_skip
                time.sleep(random.uniform(2, 4))

            except Exception as e:
                print(f"  [에러] Skip {current_skip}: {e}")
                break

        print(">>> [바이코리아] 수집 완료")