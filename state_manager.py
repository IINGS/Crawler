# state_manager.py
import json
import os
import sqlite3
import hashlib
from datetime import datetime

class StateManager:
    def __init__(self, group_name):
        self.group_name = group_name
        self.ckpt_file = 'checkpoint.json'
        self.db_file = 'local_cache.db'
        self._init_db()

    def _init_db(self):
        """로컬 캐시 DB 초기화 (SQLite)"""
        with sqlite3.connect(self.db_file) as conn:
            # 고유키, 데이터해시, 마지막확인시간
            conn.execute('''
                CREATE TABLE IF NOT EXISTS records (
                    key TEXT PRIMARY KEY, 
                    data_hash TEXT, 
                    last_updated TIMESTAMP
                )
            ''')

    # --- 기능 1: 이어하기 (Checkpoint) ---
    def load_checkpoint(self):
        """저장된 마지막 Skip 값을 불러옵니다."""
        if not os.path.exists(self.ckpt_file):
            return 0
        try:
            with open(self.ckpt_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get(self.group_name, 0)
        except:
            return 0

    def save_checkpoint(self, val):
        """현재 진행 중인 Skip 값을 저장합니다."""
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
        """처음부터 다시 하고 싶을 때 호출 (예: 월간 업데이트 시)"""
        self.save_checkpoint(0)

    # --- 기능 2: 초고속 업데이트 (Delta Crawling) ---
    def is_new_or_changed(self, unique_key, data_dict):
        """
        데이터가 변했는지 로컬 DB와 비교합니다.
        True 리턴: GAS 전송 필요 (신규 or 변경됨)
        False 리턴: GAS 전송 불필요 (똑같음)
        """
        # 1. 데이터의 지문(Hash) 생성 (순서 영향 없게 정렬)
        data_str = json.dumps(data_dict, sort_keys=True, ensure_ascii=False)
        new_hash = hashlib.md5(data_str.encode()).hexdigest()
        
        with sqlite3.connect(self.db_file) as conn:
            cur = conn.cursor()
            cur.execute("SELECT data_hash FROM records WHERE key=?", (unique_key,))
            row = cur.fetchone()
            
            # 2. 변경 없음: 로컬 캐시와 해시가 같으면 전송 스킵
            if row and row[0] == new_hash:
                # 마지막 확인 시간만 업데이트 (생존 신고)
                cur.execute("UPDATE records SET last_updated=? WHERE key=?", 
                            (datetime.now(), unique_key))
                return False 
            
            # 3. 변경 있음: DB 업데이트 후 True 리턴
            cur.execute("""
                INSERT OR REPLACE INTO records (key, data_hash, last_updated) 
                VALUES (?, ?, ?)
            """, (unique_key, new_hash, datetime.now()))
            
            return True