# crawler_core.py
import re
import requests
import json
import config
import time
import random

class DataProcessor:
    def __init__(self, source_name):
        self.webhook_url = config.WEBHOOK_URL
        self.source_name = source_name
        self.KEY_MAP = {
            # 대표자명
            'CEO': '대표자명', 'ceo': '대표자명', '대표자': '대표자명',
            # 팩스 관련
            'fax': '팩스', 'FAX': '팩스', 'Fax': '팩스', '팩스번호': '팩스',
            # 이메일 관련
            'email': '이메일', 'Email': '이메일', 'E-mail': '이메일', '메일주소': '이메일',
            # 홈페이지 관련
            'homepage': '홈페이지', 'Homepage': '홈페이지', 'Web': '홈페이지', '웹사이트': '홈페이지',
            # 전화번호/주소 관련
            'tel': '전화번호', 'Tel': '전화번호', '연락처': '전화번호',
            'addr': '주소', 'Address': '주소'
        }

    def clean_text(self, text):
        """특수문자 제거 및 정규화 (키 생성용)"""
        if not text:
            return ""
        text = re.sub(r'\(.*?\)|주식회사|유한회사|합자회사|사단법인|재단법인', '', text)
        text = re.sub(r'[^가-힣a-zA-Z0-9]', '', text)
        return text

    def create_record(self, raw_company, raw_ceo, extra_data):
        """
        GAS로 보낼 데이터 한 줄 생성
        """
        clean_comp = self.clean_text(raw_company)
        clean_ceo = self.clean_text(raw_ceo)
        
        # 고유키 생성
        final_comp = clean_comp if clean_comp else raw_company
        final_ceo = clean_ceo if clean_ceo else raw_ceo
        unique_key = f"{final_comp}_{final_ceo}"

        # 용어 표준화
        normalized_data = {}
        if extra_data:
            for key, value in extra_data.items():
                clean_key = key.strip()
                standard_key = self.KEY_MAP.get(clean_key, 
                               self.KEY_MAP.get(clean_key.lower(), clean_key))
                normalized_data[standard_key] = value

        # 1~4열 고정 컬럼 (한글 키 사용)
        record = {
            "기업명": raw_company,      # 1열
            "대표자명": raw_ceo,        # 2열
            "고유키": unique_key,       # 3열
            "수집출처": self.source_name # 4열
        }

        # 나머지 데이터 병합 (5열~)
        record.update(normalized_data)

        return record

    def send_to_gas(self, data_list):
        """GAS로 데이터를 전송하되, 실패 시 최대 5번까지 재시도합니다."""
        if not data_list:
            return None

        max_retries = 5  # 최대 5번 재시도
        base_wait = 2    # 기본 대기 시간 2초

        for attempt in range(max_retries):
            try:
                payload = {'data': data_list}
                headers = {'Content-Type': 'application/json'}
                
                # 타임아웃을 넉넉하게 60초로 설정 (GAS Lock 대기 시간 고려)
                response = requests.post(
                    self.webhook_url, 
                    data=json.dumps(payload), 
                    headers=headers,
                    timeout=60 
                )
                
                # 성공 (200 OK)
                if response.status_code == 200:
                    resp_json = response.json()
                    
                    # GAS 내부에서 "error"라고 응답한 경우 (Lock 실패 등)
                    if resp_json.get("result") == "error":
                        error_msg = resp_json.get("msg", "Unknown Error")
                        # Lock 관련 에러면 재시도
                        if "Lock" in error_msg or "Timeout" in error_msg:
                            wait_time = base_wait * (attempt + 1) + random.uniform(0, 1)
                            print(f"    [GAS 붐빔] 대기열 꽉 참. {wait_time:.1f}초 후 재시도 ({attempt+1}/{max_retries})")
                            time.sleep(wait_time)
                            continue
                        else:
                            # 로직 에러면 재시도 없이 바로 출력
                            print(f"    [GAS 에러] {error_msg}")
                            return resp_json

                    return resp_json

                # 서버 에러 (500, 502, 503 등) -> 재시도 대상
                elif response.status_code >= 500:
                    wait_time = base_wait * (attempt + 1)
                    print(f"    [서버 에러 {response.status_code}] {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                    continue
                
                else:
                    print(f"    [전송 실패] 상태 코드: {response.status_code}")
                    return None

            except Exception as e:
                # 네트워크 연결 에러 등
                wait_time = base_wait * (attempt + 1)
                print(f"    [통신 에러] {e} -> {wait_time}초 후 재시도...")
                time.sleep(wait_time)
        
        print("    !! [최종 실패] 5번 시도했으나 전송하지 못했습니다. (데이터 유실 주의)")
        return None