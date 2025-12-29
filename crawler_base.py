# crawler_base.py
import time
import random
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import config
from crawler_core import DataProcessor
from state_manager import StateManager
from smart_extractor import SmartExtractor

class BaseCrawler:
    def __init__(self, group_name, source_name, checkpoint_key=None):
        self.group_name = group_name
        self.processor = DataProcessor(source_name)
        self.save_key = checkpoint_key if checkpoint_key else group_name
        self.state = StateManager(group_name)
        self.smart_engine = SmartExtractor()

    # [Helper] 로그에 항상 출처를 붙여주는 함수
    def log(self, message):
        print(f"[{self.processor.source_name}] {message}")

    def _get_headers(self):
        return {
            'User-Agent': random.choice(config.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }

    def get_soup(self, url, params=None):
        try:
            resp = requests.get(url, params=params, headers=self._get_headers(), timeout=10)
            if resp.status_code != 200: return None
            return BeautifulSoup(resp.text, 'html.parser')
        except Exception as e:
            self.log(f"접속 에러: {e}")
            return None

    def post_json(self, url, data=None, params=None):
        try:
            resp = requests.post(url, data=data, params=params, headers=self._get_headers(), timeout=10)
            if resp.status_code != 200: return None
            return resp.json()
        except Exception:
            return None

    def fetch_parallel(self, items, worker_func, max_workers=10):
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = executor.map(worker_func, items)
            for res in futures:
                if res: results.append(res)
        return results

    def fetch_items(self, page):
        raise NotImplementedError

    def run(self):
        self.log(f"수집 시작 (Page/Skip 기반)")
        
        saved_page = self.state.load_checkpoint()
        current_page = saved_page if saved_page > 0 else 1
        
        while True:
            self.log(f"{current_page} 페이지 처리 중...")
            
            try:
                items = self.fetch_items(current_page)
                
                if not items:
                    self.log("데이터 없음. 수집 종료.")
                    self.state.reset_checkpoint()
                    break

                batch_data = []
                for item in items:
                    raw_comp = item.pop("기업명", "") 
                    raw_ceo = item.pop("대표자명", "")
                    
                    record = self.processor.create_record(raw_comp, raw_ceo, item)
                    
                    if self.state.is_new_or_changed(record['고유키'], record):
                        batch_data.append(record)

                if batch_data:
                    self.log(f"스마트 엔진 작동 ({len(batch_data)}건 분석 중...)")
                    enhanced_data = self.smart_engine.process_batch(batch_data, max_workers=10)
                    # send_to_gas 내부에서 "GAS 전송 완료" 출력함
                    self.processor.send_to_gas(enhanced_data)
                else:
                    self.log("변경사항 없음 (Skip)")
                
                self.state.save_checkpoint(current_page + 1)
                current_page += 1
                time.sleep(random.uniform(1, 2))

            except Exception as e:
                self.log(f"에러 발생: {e}")
                break