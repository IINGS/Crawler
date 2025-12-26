import json
import os
import sqlite3
import hashlib
from datetime import datetime

class StateManager:
    def __init__(self, group_name):
        self.group_name = group_name
        self.ckpt_file = 'checkpoint.json' # 체크포인트 파일은 찾기 쉽게 바깥에 둡니다.
        
        # [변경] 1. DB 저장용 폴더 이름 지정
        self.db_folder = 'local_cache'
        
        # [변경] 2. 폴더가 없으면 자동으로 생성 (mkdir)
        if not os.path.exists(self.db_folder):
            os.makedirs(self.db_folder)
            
        # [변경] 3. 경로 결합: local_cache/사이트이름.db
        # ex) local_cache/buykorea_org.db
        self.db_file = os.path.join(self.db_folder, f"{self.group_name}.db")
        
        self._init_db()

    def _init_db(self):
        """로컬 캐시 DB 초기화"""
        # 폴더 안에 DB 파일이 생성됩니다.
        with sqlite3.connect(self.db_file) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS records (
                    key TEXT PRIMARY KEY, 
                    data_hash TEXT, 
                    last_updated TIMESTAMP
                )
            ''')

    # --- 이어하기 기능 (Checkpoint) ---
    def load_checkpoint(self):
        if not os.path.exists(self.ckpt_file): return 0
        try:
            with open(self.ckpt_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get(self.group_name, 0)
        except: return 0

    def save_checkpoint(self, val):
        data = {}
        if os.path.exists(self.ckpt_file):
            try:
                with open(self.ckpt_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except: pass
        data[self.group_name] = val
        with open(self.ckpt_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def reset_checkpoint(self):
        self.save_checkpoint(0)

    # --- 스마트 업데이트 (버전 태깅 포함) ---
    def is_new_or_changed(self, unique_key, data_dict, version_tag="v1"):
        """
        데이터가 변경되었는지 확인 (버전 태그 기능 포함)
        """
        data_str = json.dumps(data_dict, sort_keys=True, ensure_ascii=False)
        combined_str = data_str + version_tag 
        new_hash = hashlib.md5(combined_str.encode()).hexdigest()
        
        with sqlite3.connect(self.db_file) as conn:
            cur = conn.cursor()
            cur.execute("SELECT data_hash FROM records WHERE key=?", (unique_key,))
            row = cur.fetchone()
            
            if row and row[0] == new_hash:
                # 변경 없음
                cur.execute("UPDATE records SET last_updated=? WHERE key=?", 
                            (datetime.now(), unique_key))
                return False 
            
            # 변경 있음 (업데이트)
            cur.execute("""
                INSERT OR REPLACE INTO records (key, data_hash, last_updated) 
                VALUES (?, ?, ?)
            """, (unique_key, new_hash, datetime.now()))
            
            return True