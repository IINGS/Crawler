# crawler_core.py (8열 고정 구조 적용)
import re
import requests
import json
import time
import random
import config

class DataProcessor:
    def __init__(self, source_name):
        self.webhook_url = config.WEBHOOK_URL
        self.source_name = source_name 
        
        self.KEY_MAP = {
            # 대표자명
            'CEO': '대표자명', 'ceo': '대표자명', '대표자': '대표자명',
            # 팩스 (고정 7열)
            'fax': '팩스', 'FAX': '팩스', 'Fax': '팩스', '팩스번호': '팩스',
            # 이메일 (고정 8열)
            'email': '이메일', 'Email': '이메일', 'E-mail': '이메일', '메일주소': '이메일',
            # 홈페이지 (고정 5열)
            'homepage': '홈페이지', 'Homepage': '홈페이지', 'Web': '홈페이지', '웹사이트': '홈페이지',
            # 전화번호 (고정 6열)
            'tel': '전화번호', 'Tel': '전화번호', '연락처': '전화번호',
            # 주소 (자유 항목으로 이동)
            'addr': '주소', 'Address': '주소'
        }
        
        # [수정] 아예 무시할 키워드 (혹시 수집되더라도 시트에 안 넣음)
        self.IGNORED_KEYS = ['국가', '설립일', '설립연도', 'Country', 'Establishment']

    def remove_corporate_tags(self, text):
        """법인명(주식회사 등)만 제거"""
        if not text: return ""
        text = re.sub(r'\((주|유|합|자|재|사|주식회사|유한회사|합자회사|사단법인|재단법인)\)', '', text)
        text = re.sub(r'주식회사|유한회사|합자회사|사단법인|재단법인', '', text)
        return text.strip()

    def create_record(self, raw_company, raw_ceo, extra_data):
        # 1. 고유키 생성 (엄격 정제)
        key_comp = re.sub(r'[^가-힣a-zA-Z0-9]', '', raw_company) 
        key_ceo = re.sub(r'[^가-힣a-zA-Z0-9]', '', raw_ceo)
        unique_key = f"{key_comp}_{key_ceo}"

        # 2. 보여주기용 데이터
        final_comp = self.remove_corporate_tags(raw_company)
        final_ceo = raw_ceo.strip() if raw_ceo else ""

        # 3. 기본 레코드 구조 (1~4열)
        record = {
            "기업명": final_comp,     # 1열
            "대표자명": final_ceo,    # 2열
            "고유키": unique_key,     # 3열
            "수집출처": self.source_name, # 4열
            # 5~8열 자리 확보 (없어도 빈카으로라도 나가게 초기화)
            "홈페이지": "",           # 5열
            "전화번호": "",           # 6열
            "팩스": "",              # 7열
            "이메일": ""             # 8열
        }

        # 4. 추가 데이터 매핑 및 병합
        if extra_data:
            for key, value in extra_data.items():
                clean_key = key.strip()
                
                # 무시할 키면 건너뜀
                if any(x in clean_key for x in self.IGNORED_KEYS):
                    continue

                standard_key = self.KEY_MAP.get(clean_key, 
                               self.KEY_MAP.get(clean_key.lower(), clean_key))
                
                # 값 처리
                if isinstance(value, (list, set)):
                    str_val = ", ".join(list(value))
                else:
                    str_val = str(value)
                
                str_val = str_val.strip()

                # [중요] record 딕셔너리에 업데이트
                # 만약 '홈페이지' 같은 고정 키라면 위에서 만든 빈칸이 채워짐
                # '주소' 같은 새로운 키라면 딕셔너리 뒤에 추가됨 (-> 자연스럽게 9열 이후로 배치)
                record[standard_key] = str_val

        return record

    def send_to_gas(self, data_list):
        if not data_list: return None

        print(f"\n    [데이터 확인] 구조 변경 샘플:")
        print(f"      - [1]기업: {data_list[0].get('기업명')}")
        print(f"      - [5]홈피: {data_list[0].get('홈페이지')}")
        print(f"      - [6]전화: {data_list[0].get('전화번호')}")
        print(f"      - [7]팩스: {data_list[0].get('팩스')}")
        print(f"      - [8]메일: {data_list[0].get('이메일')}")

        max_retries = 5
        base_wait = 2

        for attempt in range(max_retries):
            try:
                payload = {'data': data_list}
                headers = {'Content-Type': 'application/json'}
                
                response = requests.post(
                    self.webhook_url, 
                    data=json.dumps(payload), 
                    headers=headers,
                    timeout=60 
                )
                
                if response.status_code == 200:
                    resp_json = response.json()
                    if resp_json.get("result") == "error":
                        error_msg = resp_json.get("msg", "Unknown Error")
                        if "Lock" in error_msg or "Timeout" in error_msg:
                            wait_time = base_wait * (attempt + 1) + random.uniform(0, 1)
                            print(f"    [GAS 붐빔] 대기열 꽉 참. {wait_time:.1f}초 후 재시도...")
                            time.sleep(wait_time)
                            continue
                        else:
                            print(f"    [GAS 에러] {error_msg}")
                            return resp_json
                    return resp_json

                elif response.status_code >= 500:
                    wait_time = base_wait * (attempt + 1)
                    print(f"    [서버 에러 {response.status_code}] 재시도...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"    [전송 실패] {response.status_code}")
                    return None

            except Exception as e:
                wait_time = base_wait * (attempt + 1)
                print(f"    [통신 에러] {e} -> 재시도...")
                time.sleep(wait_time)
        
        print("    !! [최종 실패] 전송 불가")
        return None