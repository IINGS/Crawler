# crawler_core.py
import re
import requests
import json
import config

class DataProcessor:
    def __init__(self, source_name):
        self.webhook_url = config.WEBHOOK_URL
        self.source_name = source_name
        self.KEY_MAP = {
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
        # (주), (유) 등 제거
        text = re.sub(r'\(.*?\)|주식회사|유한회사|합자회사|사단법인|재단법인', '', text)
        # 한글, 영문, 숫자만 남김
        text = re.sub(r'[^가-힣a-zA-Z0-9]', '', text)
        return text

    def create_record(self, raw_company, raw_ceo, extra_data):
        """
        GAS로 보낼 데이터 한 줄을 생성합니다.
        이제 extra_data의 키(Key)를 자동으로 표준화합니다.
        """
        clean_comp = self.clean_text(raw_company)
        clean_ceo = self.clean_text(raw_ceo)
        
        # 키 생성
        final_comp = clean_comp if clean_comp else raw_company
        final_ceo = clean_ceo if clean_ceo else raw_ceo
        unique_key = f"{final_comp}_{final_ceo}"

        # [변경 3] 용어 표준화(Cleaning) 작업
        normalized_data = {}
        if extra_data:
            for key, value in extra_data.items():
                clean_key = key.strip() # 공백 제거
                
                # 사전에서 표준 용어 찾기 (없으면 원래 키 사용)
                # 1차 시도: 원래 키로 검색 / 2차 시도: 소문자로 검색
                standard_key = self.KEY_MAP.get(clean_key, 
                               self.KEY_MAP.get(clean_key.lower(), clean_key))
                
                normalized_data[standard_key] = value

        # [변경 4] 기본 정보 + 출처 자동 삽입
        record = {
            "Raw_Company": raw_company, 
            "Unique_Key": unique_key,
            "수집_출처": self.source_name  # __init__에서 받은 이름 사용
        }

        # 표준화된 추가 데이터 병합
        record.update(normalized_data)

        return record

    def send_to_gas(self, data_list):
        """데이터 리스트를 GAS로 전송"""
        if not data_list:
            return None

        try:
            payload = {'data': data_list}
            headers = {'Content-Type': 'application/json'}
            
            response = requests.post(
                self.webhook_url, 
                data=json.dumps(payload), 
                headers=headers,
                timeout=15
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"[전송 실패] 상태 코드: {response.status_code}")
                return None
        except Exception as e:
            print(f"[전송 에러] {e}")
            return None