import math
import time
import random
import requests
from crawler_base import BaseCrawler

class BookkCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("bookk_co_kr", "부크크")
        
        self.api_url = "https://api.bookk.co.kr/bookStores/products"
        self.req_size = 30
        
        # c2 ~ c207까지 모든 카테고리 ID를 콤마로 연결 (통합 URL용)
        self.all_genres_param = ",".join([f"c{i}" for i in range(2, 208)])

    def _get_api_data(self, page):
        """API 요청"""
        params = {
            'genres': self.all_genres_param,
            'limit': self.req_size,
            'page': page,
            'sort': '-createdAt'
        }
        try:
            resp = requests.get(self.api_url, params=params, headers=self._get_headers(), timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            self.log(f"API 요청 실패 (p{page}): {e}")
        return None

    def run(self):
        self.log("부크크(Bookk) 통합 모드 수집 시작 (c2~c207)")

        # 1. 첫 페이지 정찰
        first_data = self._get_api_data(1)
        if not first_data:
            self.log("첫 페이지 응답 없음. 종료.")
            return

        total_count = first_data.get('count', 0)
        if total_count == 0:
            self.log("게시물이 하나도 없습니다. 종료.")
            return

        total_pages = math.ceil(total_count / self.req_size)
        
        # 2. 체크포인트 로드 (다른 모듈과 동일하게 0이면 1부터 시작)
        saved_page = self.state.load_checkpoint()
        start_page = saved_page if saved_page > 0 else 1
        
        self.log(f"총 {total_count}개 도서 ({total_pages}페이지) 확인.")
        self.log(f"▶ 이어하기: {start_page}페이지부터 수집을 시작합니다.")

        # 3. 페이지 순회
        for page in range(start_page, total_pages + 1):
            self.log(f"{page}/{total_pages} 페이지 처리 중...")
            
            data = self._get_api_data(page)
            items = data.get('rows', []) if data else []

            # 데이터가 비어있어도 카운트는 진행 (삭제된 데이터 등 고려)
            if not items:
                self.state.save_checkpoint(page + 1)
                continue

            batch_data = []

            # 4. 아이템 처리
            for item in items:
                extras = item.get('extras', {})
                author_info = extras.get('author', {})
                content = item.get('content', {})
                
                # [수정됨] 저자명: 닉네임 대체 없이, 없으면 공백("")
                author_name = content.get('author', '')
                if not author_name:
                    author_name = ""

                # Account ID 확인 (필터링용)
                account_id = author_info.get('accountId', '')
                
                # [필터링] 네이버/카카오 로그인 계정 제외
                if account_id.startswith('naver_') or account_id.startswith('kakao_'):
                    continue
                
                # 책 제목
                title = item.get('title', '')
                if not title:
                    title = item.get('name', '')

                # 구글 검색 URL
                google_search_url = f'https://www.google.com/search?q=%22{account_id}%22'
                
                # 출판 날짜 (createdAt)
                created_at = item.get('createdAt', '')
                if created_at and len(created_at) >= 10:
                    created_at = created_at[:10]

                # 커스텀 데이터 구성
                custom_extra_data = {
                    "Homepage": google_search_url,
                    "accountId": account_id,
                    "createdAt": created_at
                }

                # 레코드 생성 (제목, 저자명, 커스텀데이터)
                record = self.processor.create_record(title, author_name, custom_extra_data)
                
                # 중복 체크
                if self.state.is_new_or_changed(record['고유키'], record):
                    batch_data.append(record)

            # 5. 전송
            if batch_data:
                self.log(f"유효 데이터 {len(batch_data)}건 전송...")
                enhanced_data = self.smart_engine.process_batch(batch_data, max_workers=5)
                self.processor.send_to_gas(enhanced_data)
            
            # 6. 체크포인트 저장 (현재 페이지 완료 후 다음 페이지 저장)
            self.state.save_checkpoint(page + 1)
            
            time.sleep(random.uniform(0.5, 1.2))
            
        self.log("부크크 수집 완료.")
        self.state.save_checkpoint(1)