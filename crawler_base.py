# crawler_base.py
import os
import glob
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

class BaseFileCrawler(BaseCrawler):
    def __init__(self, group_name, source_name, target_folder=None):
        """
        :param group_name: 상태 관리를 위한 그룹명 (DB파일 이름 등)
        :param source_name: GAS 전송 시 표기할 출처명
        :param target_folder: 'FilesToParse' 아래에 위치할 폴더명 (예: 'localdata_hospital')
        """
        self.group_name = group_name
        self.processor = DataProcessor(source_name)
        self.state = StateManager(group_name)
        self.smart_engine = SmartExtractor()
        folder_name = target_folder if target_folder else group_name
        
        # 파일 경로 설정: FilesToParse/{target_folder}
        self.base_dir = os.path.join("FilesToParse", folder_name)

    def log(self, message):
        print(f"[{self.processor.source_name}] {message}")

    def process_file(self, file_path):
        """개별 파일을 처리하는 로직 (자식 클래스에서 구현)"""
        raise NotImplementedError

    def run(self):
        self.log(f"파일 파싱 모드 시작 (폴더: {self.base_dir})")

        # 1. 폴더 확인
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)
            self.log(f"폴더가 생성되었습니다: {self.base_dir}")
            self.log("이 폴더에 분석할 파일들을 넣고 다시 실행해주세요.")
            return

        # 2. 파일 목록 로드 (이름순 정렬 필수 - 순서 보장 위해)
        # xml 파일뿐만 아니라 필요하다면 다른 확장자도 처리 가능하게 glob 사용
        files = sorted(glob.glob(os.path.join(self.base_dir, "*.*")))
        if not files:
            self.log("폴더에 파일이 없습니다.")
            return

        # 3. 체크포인트 확인 (마지막으로 완료한 파일명)
        last_done_file = self.state.load_checkpoint()
        if last_done_file == 0:
            last_done_file = "" # 문자열 비교를 위해 초기화
        
        skip_mode = True if last_done_file else False
        
        self.log(f"총 {len(files)}개 파일 발견.")
        if skip_mode:
            self.log(f"▶ 이어하기: '{last_done_file}' 다음 파일부터 시작합니다.")

        # 4. 파일 순회
        for file_path in files:
            file_name = os.path.basename(file_path)

            # 이어하기 로직: 체크포인트 파일까지는 건너뜀
            if skip_mode:
                if file_name == last_done_file:
                    skip_mode = False # 찾았다! 다음 파일부터 처리
                continue

            self.log(f"📂 파일 처리 시작: {file_name}")
            
            try:
                # 자식 클래스의 process_file 호출
                self.process_single_file(file_path)
                
                # 파일 하나가 끝날 때마다 체크포인트 저장 (파일명)
                self.state.save_checkpoint(file_name)
                
            except Exception as e:
                self.log(f"❌ 처리 중 에러 발생 ({file_name}): {e}")
                # 에러 발생 시 멈춤 (문제 해결 후 다시 돌리기 위해)
                break
        
        self.log("모든 파일 처리 완료.")

    def process_single_file(self, file_path):
        # 자식 클래스가 구현하지 않았을 경우 대비
        raise NotImplementedError("process_single_file 메서드를 구현해야 합니다.")