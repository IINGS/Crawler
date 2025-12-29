# crawler_core.py
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
            'CEO': '대표자명', 'ceo': '대표자명', '대표자': '대표자명',
            'fax': '팩스', 'FAX': '팩스', 'Fax': '팩스', '팩스번호': '팩스',
            'email': '이메일', 'Email': '이메일', 'E-mail': '이메일', '메일주소': '이메일',
            'homepage': '홈페이지', 'Homepage': '홈페이지', 'Web': '홈페이지', '웹사이트': '홈페이지',
            'tel': '전화번호', 'Tel': '전화번호', '연락처': '전화번호',
            'addr': '주소', 'Address': '주소'
        }
        self.IGNORED_KEYS = ['국가', '설립일', '설립연도', 'Country', 'Establishment']

    def remove_corporate_tags(self, text):
        if not text: return ""
        text = re.sub(r'\((주|유|합|자|재|사|주식회사|유한회사|합자회사|사단법인|재단법인)\)', '', text)
        text = re.sub(r'주식회사|유한회사|합자회사|사단법인|재단법인', '', text)
        return text.strip()

    def create_record(self, raw_company, raw_ceo, extra_data):
        # (기존 로직 동일)
        key_comp = re.sub(r'[^가-힣a-zA-Z0-9]', '', raw_company) 
        key_ceo = re.sub(r'[^가-힣a-zA-Z0-9]', '', raw_ceo)
        unique_key = f"{key_comp}_{key_ceo}"

        final_comp = self.remove_corporate_tags(raw_company)
        final_ceo = raw_ceo.strip() if raw_ceo else ""

        record = {
            "기업명": final_comp,
            "대표자명": final_ceo,
            "고유키": unique_key,
            "수집출처": self.source_name,
            "홈페이지": "", "전화번호": "", "팩스": "", "이메일": ""
        }

        if extra_data:
            for key, value in extra_data.items():
                clean_key = key.strip()
                if any(x in clean_key for x in self.IGNORED_KEYS): continue
                
                standard_key = self.KEY_MAP.get(clean_key, self.KEY_MAP.get(clean_key.lower(), clean_key))
                
                if isinstance(value, (list, set)): str_val = ", ".join(list(value))
                else: str_val = str(value)
                
                record[standard_key] = str_val.strip()

        return record

    def send_to_gas(self, data_list):
        if not data_list: return None

        # [삭제됨] 구조 샘플 출력 코드 제거

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
                            print(f"[{self.source_name}] GAS 붐빔 (대기열 Full). {wait_time:.1f}초 후 재시도...")
                            time.sleep(wait_time)
                            continue
                        else:
                            print(f"[{self.source_name}] GAS 에러: {error_msg}")
                            return resp_json
                    
                    # [추가] 전송 완료 로그 (출처 포함)
                    print(f"[{self.source_name}] >> GAS 전송 완료 ({len(data_list)}건)")
                    return resp_json

                elif response.status_code >= 500:
                    wait_time = base_wait * (attempt + 1)
                    print(f"[{self.source_name}] 서버 에러 {response.status_code}. 재시도...")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[{self.source_name}] 전송 실패 (Status: {response.status_code})")
                    return None

            except Exception as e:
                wait_time = base_wait * (attempt + 1)
                print(f"[{self.source_name}] 통신 에러: {e} -> 재시도...")
                time.sleep(wait_time)
        
        print(f"[{self.source_name}] !! 최종 전송 실패")
        return None