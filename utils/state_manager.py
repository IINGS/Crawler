import sqlite3
import hashlib
import json
import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor

class StateManager:
    def __init__(self, domain_group, db_dir="states"):
        self.domain_group = domain_group 
        self.db_dir = db_dir
        
        if not os.path.exists(self.db_dir):
            os.makedirs(self.db_dir, exist_ok=True)
            
        self.db_path = os.path.join(self.db_dir, f"crawl_state_{domain_group}.db")
        self.logger = logging.getLogger(f"StateManager-{domain_group}")
        self.executor = ThreadPoolExecutor(max_workers=1)
        self._init_db()

    def _init_db(self):
        """DB 초기화 (동기 실행)"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # 수집된 아이템 해시 저장 (중복 방지)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS items (
                        item_hash TEXT PRIMARY KEY,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                # 체크포인트 저장
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS checklist (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                ''')
                conn.commit()
        except Exception as e:
            self.logger.error(f"DB Init Failed: {e}")

    def _calculate_hash(self, data: dict) -> str:
        """데이터의 고유 해시값 생성"""
        unique_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(unique_str.encode('utf-8')).hexdigest()

    async def is_new(self, item: dict) -> bool:
        """(비동기) 새로운 데이터인지 확인하고, 새로우면 DB에 등록"""
        item_hash = self._calculate_hash(item)
        loop = asyncio.get_running_loop()
        
        exists = await loop.run_in_executor(
            self.executor, self._check_and_insert, item_hash
        )
        return not exists

    def _check_and_insert(self, item_hash):
        """(동기) 실제 DB 조회 및 삽입"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM items WHERE item_hash = ?", (item_hash,))
                if cursor.fetchone():
                    return True # 이미 존재함
                
                cursor.execute("INSERT INTO items (item_hash) VALUES (?)", (item_hash,))
                conn.commit()
                return False # 새로운 데이터
        except Exception as e:
            self.logger.error(f"DB Error: {e}")
            return True # 에러 발생 시 중복으로 처리하여 안전장치

    async def save_checkpoint(self, key, value):
        """(비동기) 진행 상황 저장"""
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._save_checkpoint_sync, key, str(value))

    def _save_checkpoint_sync(self, key, value):
        with sqlite3.connect(self.db_path) as conn:
            conn.cursor().execute(
                "INSERT OR REPLACE INTO checklist (key, value) VALUES (?, ?)", 
                (key, value)
            )
            conn.commit()

    async def get_checkpoint(self, key, default=None):
        loop = asyncio.get_running_loop()
        val = await loop.run_in_executor(None, self._get_checkpoint_sync, key)
        return val if val else default

    def _get_checkpoint_sync(self, key):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM checklist WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row[0] if row else None