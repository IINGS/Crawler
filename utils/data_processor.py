import re
import json
import logging
import asyncio
import random
import aiohttp
from config import WEBHOOK_URL

class DataProcessor:
    # 모든 크롤러가 공유하는 '전역 컨베이어 벨트' (Queue)
    _global_queue = asyncio.Queue()
    _worker_task = None
    _logger = logging.getLogger("GlobalProcessor")

    def __init__(self, source_name="Unknown"):
        self.source_name = source_name
        self.logger = logging.getLogger(f"DataProcessor-{source_name}")
        
        # 키 매핑 설정
        self.KEY_MAP = {
            'CEO': '대표자명', 'ceo': '대표자명', '대표자': '대표자명',
            'fax': '팩스', 'FAX': '팩스', 'Fax': '팩스', '팩스번호': '팩스',
            'email': '이메일', 'Email': '이메일', 'E-mail': '이메일', '메일주소': '이메일',
            'homepage': '홈페이지', 'Homepage': '홈페이지', 'Web': '홈페이지', '웹사이트': '홈페이지',
            'tel': '전화번호', 'Tel': '전화번호', '연락처': '전화번호',
            'addr': '주소', 'Address': '주소'
        }
        self.IGNORED_KEYS = ['국가', '설립일', '설립연도', 'Country', 'Establishment']

    @classmethod
    async def start_worker(cls):
        """백그라운드 배송 트럭 시동 걸기"""
        if cls._worker_task is None:
            cls._logger.info("🚚 Data Upload Worker Started...")
            cls._worker_task = asyncio.create_task(cls._process_queue_loop())

    @classmethod
    async def stop_worker(cls):
        """작업 종료 및 남은 데이터 처리"""
        if cls._worker_task:
            cls._logger.info("🛑 Waiting for remaining data to upload...")
            await cls._global_queue.join() # 큐가 빌 때까지 대기
            cls._worker_task.cancel()
            try:
                await cls._worker_task
            except asyncio.CancelledError:
                pass
            cls._logger.info("✅ All Uploads Finished.")

    @classmethod
    async def _process_queue_loop(cls):
        """큐에서 데이터를 꺼내 GAS로 보내는 무한 루프"""
        batch_size = 150
        buffer = []
        
        while True:
            try:
                # 1. 큐에서 아이템 하나 꺼냄
                item = await cls._global_queue.get()
                buffer.append(item)
                
                # 2. 버퍼가 찰 때까지 추가로 꺼냄 (기다리지 않고 있는 거 다 긁어모음)
                while len(buffer) < batch_size:
                    try:
                        # 0.1초 안에 더 들어오는게 있으면 같이 보냄
                        extra_item = await asyncio.wait_for(cls._global_queue.get(), timeout=0.1)
                        buffer.append(extra_item)
                    except asyncio.TimeoutError:
                        break # 더 없으면 그냥 보냄
                
                # 3. GAS 전송
                if buffer:
                    await cls._send_batch_to_gas(list(buffer))
                    # 큐 작업 완료 신호 (buffer 개수만큼)
                    for _ in range(len(buffer)):
                        cls._global_queue.task_done()
                    buffer.clear()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                cls._logger.error(f"Worker Error: {e}")

    @classmethod
    async def _send_batch_to_gas(cls, data_list):
        """실제 HTTP 전송 로직"""
        if not data_list: return

        # 로그에 어떤 출처의 데이터가 섞여있는지 표시
        sources = set(d.get("수집출처", "Unknown") for d in data_list)
        cls._logger.info(f"📤 Uploading batch of {len(data_list)} items (Sources: {', '.join(sources)})")

        max_retries = 10
        payload = {'data': data_list}
        headers = {'Content-Type': 'application/json'}

        for attempt in range(max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        WEBHOOK_URL, 
                        data=json.dumps(payload, ensure_ascii=False), 
                        headers=headers,
                        timeout=45
                    ) as response:
                        
                        if response.status == 200:
                            resp_json = await response.json()
                            if resp_json.get("result") == "busy":
                                wait = (2 ** attempt) + random.uniform(1, 3)
                                cls._logger.warning(f"⚠️ GAS Busy. Retry in {wait:.1f}s...")
                                await asyncio.sleep(wait)
                                continue
                            
                            if resp_json.get("result") == "error":
                                cls._logger.error(f"❌ GAS Error: {resp_json.get('msg')}")
                                return

                            cls._logger.info(f"✅ Sent {len(data_list)} items.")
                            return

                        elif response.status >= 500:
                            await asyncio.sleep(3)
                            continue
                        elif response.status == 429:
                            await asyncio.sleep(5)
                            continue

            except Exception as e:
                cls._logger.error(f"⚠️ Network Error: {e}")
                await asyncio.sleep(2)
        
        cls._logger.error(f"💀 Failed to upload batch of {len(data_list)} items.")

    async def process(self, raw_item):
        """ 데이터를 큐에 넣기만 함 (즉시 리턴)"""
        cleaned_record = self.create_record(raw_item)
        # 전역 큐에 투입
        await self._global_queue.put(cleaned_record)

    async def flush(self):
        """이제 개별 flush는 필요 없음 (Global Worker가 처리)"""
        pass

    def create_record(self, raw_data):
        raw_company = raw_data.get('기업명', raw_data.get('title', ''))
        raw_ceo = raw_data.get('대표자명', raw_data.get('ceo', ''))
        
        key_comp = re.sub(r'[^가-힣a-zA-Z0-9]', '', str(raw_company)) 
        key_ceo = re.sub(r'[^가-힣a-zA-Z0-9]', '', str(raw_ceo))
        unique_key = f"{key_comp}_{key_ceo}"

        final_comp = self.remove_corporate_tags(raw_company)
        final_ceo = str(raw_ceo).strip()

        record = {
            "기업명": final_comp,
            "대표자명": final_ceo,
            "고유키": unique_key,
            "수집출처": self.source_name,
            "홈페이지": "", "전화번호": "", "팩스": "", "이메일": ""
        }

        for key, value in raw_data.items():
            if key in ['기업명', '대표자명', 'title', 'ceo']: continue
            clean_key = key.strip()
            if any(x in clean_key for x in self.IGNORED_KEYS): continue
            standard_key = self.KEY_MAP.get(clean_key, self.KEY_MAP.get(clean_key.lower(), clean_key))
            
            if isinstance(value, (list, set)): str_val = ", ".join(list(value))
            else: str_val = str(value)

            if standard_key == '전화번호':
                str_val = self._format_phone_number(str_val)
            
            record[standard_key] = str_val.strip()

        return record

    def remove_corporate_tags(self, text):
        if not text: return ""
        text = str(text)
        text = re.sub(r'\((주|유|합|자|재|사|주식회사|유한회사|합자회사|사단법인|재단법인)\)', '', text)
        text = re.sub(r'주식회사|유한회사|합자회사|사단법인|재단법인', '', text)
        return text.strip()
    
    def _format_phone_number(self, raw_tel):
        if not raw_tel: return ""
        tel = re.sub(r'[^0-9]', '', str(raw_tel))
        if tel.startswith('02'):
            if len(tel) == 9: return f"{tel[:2]}-{tel[2:5]}-{tel[5:]}"
            if len(tel) == 10: return f"{tel[:2]}-{tel[2:6]}-{tel[6:]}"
        elif len(tel) > 3 and tel.startswith('0'):
            if len(tel) == 10: return f"{tel[:3]}-{tel[3:6]}-{tel[6:]}"
            if len(tel) == 11: return f"{tel[:3]}-{tel[3:7]}-{tel[7:]}"
        elif len(tel) == 8 and tel.startswith('1'):
             return f"{tel[:4]}-{tel[4:]}"
        return raw_tel