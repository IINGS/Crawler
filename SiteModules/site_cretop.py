# SiteModules/site_cretop.py
import time
import random
from bs4 import BeautifulSoup
# [중요] playwright 대신 patchright 사용
from patchright.sync_api import sync_playwright 
from crawler_base import BaseCrawler

class CretopCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("cretop_com", "크레탑")
        self.start_url = "https://www.cretop.com/ET/SS/ETSS070M1"
        self.browser = None
        self.page = None

    def _init_browser(self, p):
        self.log("브라우저 초기화 (로컬 Chrome + 이벤트 리스너 부착)...")
        
        try:
            self.browser = p.chromium.launch(
                channel="chrome", 
                headless=False,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-infobars",
                    "--disable-gpu", 
                    "--disable-dev-shm-usage"
                ]
            )
            
            self.context = self.browser.new_context(
                viewport=None, 
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                device_scale_factor=1 
            )
            
            self.page = self.context.new_page()
            self.page.set_viewport_size({"width": 1920, "height": 1080})

            # [핵심 추가] 브라우저가 왜 죽는지 감시하는 리스너들
            self.page.on("close", lambda: self.log("❌ [SYSTEM] 페이지가 닫혔습니다! (User or Script Closed)"))
            self.page.on("crash", lambda: self.log("💥 [SYSTEM] 브라우저 프로세스 충돌(Crash)! 메모리 부족이나 호환성 문제일 수 있음."))
            self.page.on("pageerror", lambda err: self.log(f"💀 [JS ERROR] 페이지 내 치명적 스크립트 에러: {err}"))
            # self.page.on("console", lambda msg: self.log(f"💬 [CONSOLE] {msg.text}")) # 필요하면 주석 해제 (로그 너무 많을 수 있음)

        except Exception as e:
            self.log(f"초기화 중 치명적 에러: {e}")
            raise e

    # [핵심 추가] 사람처럼 마우스를 움직이고 클릭하는 함수
    def _human_click(self, locator):
        try:
            # 요소가 화면에 안정적으로 렌더링될 때까지 대기
            locator.wait_for(state="visible", timeout=5000)
            
            # 요소의 위치 정보 가져오기
            box = locator.bounding_box()
            if not box:
                # 위치를 못 찾으면 그냥 일반 클릭 (Fallback)
                locator.click()
                time.sleep(random.uniform(1.0, 2.0))
                return

            # 클릭할 좌표 계산 (요소 중심부에서 약간의 랜덤 오차 추가)
            target_x = box['x'] + box['width'] / 2 + random.uniform(-5, 5)
            target_y = box['y'] + box['height'] / 2 + random.uniform(-5, 5)

            # 1. 마우스 이동 (사람처럼 부드럽게 steps를 줘서 이동)
            self.page.mouse.move(target_x, target_y, steps=random.randint(10, 25))
            
            # 2. 호버링 (클릭 전 잠깐 멈춤)
            time.sleep(random.uniform(0.3, 0.7))
            
            # 3. 클릭
            self.page.mouse.click(target_x, target_y)
            
            # 4. 클릭 후 여유 대기 (서버가 요청을 처리할 시간 줌)
            time.sleep(random.uniform(1.0, 2.5))
            
        except Exception as e:
            self.log(f"휴먼 클릭 실패 (일반 클릭 시도): {e}")
            try:
                locator.click()
                time.sleep(1)
            except:
                pass

    def _setup_search_conditions(self):
        # 1. 페이지 접속
        target_url = "https://www.cretop.com/ET/SS/ETSS070M1"
        self.log(f"접속 시도: {target_url}")
        
        try:
            self.page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_load_state("networkidle")
        except:
            pass

        # 2. 로그인 확인
        self.log("로그인 여부 확인 중...")
        login_check_xpath = "xpath=//*[contains(text(), '정상')]"
        
        try:
            self.page.locator(login_check_xpath).first.wait_for(state="attached", timeout=3000)
            self.log("✅ 로그인 상태 확인됨.")
        except:
            self.log("📢 [60초 대기] 로그인해주세요.")
            try:
                self.page.locator(login_check_xpath).first.wait_for(state="attached", timeout=60000)
                self.log("✅ 로그인 감지됨!")
                time.sleep(2)
            except:
                self.log("❌ 로그인 시간 초과.")
                return False

        # 3. 체크박스 설정
        target_labels = ["정상", "소기업", "개인사업자"]
        self.log(f"▶ 검색 조건 설정: {target_labels}")

        for label_text in target_labels:
            try:
                xpath = f"xpath=(//*[contains(text(), '{label_text}')])[last()]/preceding::input[@type='checkbox'][1]"
                el = self.page.locator(xpath)
                
                if el.count() == 0:
                    xpath = f"xpath=(//*[contains(text(), '{label_text}')])[1]/preceding::input[@type='checkbox'][1]"
                    el = self.page.locator(xpath)
                
                if el.count() > 0:
                    if not el.is_checked():
                        el.scroll_into_view_if_needed()
                        self._human_click(el)
                        self.log(f"✅ [{label_text}] 체크 완료")
                    else:
                        self.log(f"패스: [{label_text}] 이미 체크됨")
                else:
                    self.log(f"⚠️ [{label_text}] 못 찾음")

                time.sleep(random.uniform(0.5, 1.0))
                
            except Exception as e:
                self.log(f"🚨 [{label_text}] 에러: {e}")

        # 4. 조회 버튼 클릭
        self.log("조회 버튼 클릭...")
        try:
            search_btn = self.page.locator("xpath=//button[contains(., '조회하기')]")
            if search_btn.count() > 0:
                self._human_click(search_btn)
                
                self.log("POST 요청 전송. 응답 대기...")
                self.page.wait_for_load_state("networkidle")
                self.log("결과 로딩 완료. 3초 대기...")
                time.sleep(random.uniform(3.0, 4.0)) 
            else:
                self.log("❌ '조회하기' 버튼 못 찾음")
                return False
        except Exception as e:
            self.log(f"조회 버튼 실패: {e}")
            return False

        # 5. [핵심 수정] 100개씩 보기 (키보드 조작 방식)
        self.log("100개씩 보기 설정 (키보드 우회)...")
        try:
            select_box = self.page.locator('#pageCount')
            
            # (1) 드롭다운 클릭 (포커스 맞추기 & 메뉴 열기)
            self.log("  - 1단계: 드롭다운 클릭")
            select_box.scroll_into_view_if_needed()
            self._human_click(select_box)
            time.sleep(random.uniform(1.0, 1.5))
            
            # (2) 키보드 '아래' 키 3번 입력 (10 -> 20 -> 50 -> 100)
            # select_option을 쓰지 않으므로 서버는 이를 100% 사용자의 키보드 입력으로 인식함
            self.log("  - 2단계: 키보드 입력 (ArrowDown x 3)")
            for _ in range(3):
                self.page.keyboard.press("ArrowDown")
                time.sleep(random.uniform(0.2, 0.4)) # 키 입력 사이 인간적 딜레이
            
            # (3) 엔터 키로 확정
            self.log("  - 3단계: 엔터 입력 (확정)")
            self.page.keyboard.press("Enter")
            
            # (4) 리스트 갱신 대기
            self.page.wait_for_load_state("networkidle")
            self.log("✅ 리스트 갱신 완료. 수집 시작.")
            
            time.sleep(random.uniform(3.0, 5.0))
            return True
            
        except Exception as e:
            self.log(f"⚠️ 100개 보기 설정 실패: {e}")
            return True

    def _navigate_to_checkpoint(self, target_page):
        if target_page <= 1: return

        self.log(f"🚀 {target_page}페이지로 복구 이동 시작...")
        
        jump_count = (target_page - 1) // 10
        if jump_count > 0:
            next_group_btn = self.page.locator('button.next:has(span:text-is("다음그룹"))')
            for i in range(jump_count):
                if next_group_btn.is_visible():
                    # [변경] 단순 click -> human_click
                    self._human_click(next_group_btn)
                    self.page.wait_for_load_state("networkidle")
                else:
                    break

        current = self._get_current_page_num()
        if current != target_page:
            target_btn = self.page.locator(f'ul.paging button.num:has(span:text-is("{target_page}"))')
            if target_btn.is_visible():
                self._human_click(target_btn)
                self.page.wait_for_load_state("networkidle")

    def _get_current_page_num(self):
        try:
            el = self.page.locator("ul.paging button.num.on span").first
            return int(el.inner_text().strip()) if el.is_visible() else 1
        except: return 1

    def _get_value_by_title(self, item, title):
        span = item.find('span', class_='list-tit', string=title)
        return "".join([s.get_text(strip=True) for s in span.find_next_siblings('span', class_='list-info')]) if span else ""

    def run(self):
        self.log("Patchright 브라우저 프로세스 시작...")
        
        with sync_playwright() as p:
            self._init_browser(p)
            try:
                # [중요] 설정이 성공했는지 확인
                setup_success = self._setup_search_conditions()
                
                if not setup_success:
                    self.log("⛔ 초기 설정(페이지 접속/조건설정) 실패로 인해 봇을 종료합니다.")
                    # 브라우저 닫히는 시간 벌기 위해 잠시 대기
                    time.sleep(5)
                    return # 여기서 종료!

                # --- 이하 기존 수집 로직 ---
                saved_page = self.state.load_checkpoint()
                start_page = saved_page if saved_page > 0 else 1
                if start_page > 1: self._navigate_to_checkpoint(start_page)
                
                current_page = start_page
                while True:
                    self.log(f"▶ {current_page} 페이지 수집 진입...")
                    
                    # (혹시 중간에 브라우저 꺼졌는지 확인)
                    if self.page.is_closed():
                        self.log("❌ 수집 도중 브라우저가 닫혀있습니다. 루프 종료.")
                        break
                    
                    soup = BeautifulSoup(self.page.content(), 'html.parser')
                    items = soup.select('div.result-txt-wrap')
                    if not items:
                        self.log("데이터 없음. 종료.")
                        break

                    batch_data = []
                    first_comp = ""
                    for idx, item in enumerate(items):
                        comp_span = item.select_one('button.result-layer-open span')
                        raw_comp = comp_span.get_text(strip=True) if comp_span else ""
                        if idx == 0: first_comp = raw_comp
                        
                        raw_ceo = self._get_value_by_title(item, "대표자명")
                        extra = {
                            "기업유형": self._get_value_by_title(item, "기업유형/형태"),
                            "사업자번호": self._get_value_by_title(item, "사업자번호"),
                            "산업분류": self._get_value_by_title(item, "산업분류"),
                            "주소": self._get_value_by_title(item, "주소")
                        }
                        record = self.processor.create_record(raw_comp, raw_ceo, extra)
                        if self.state.is_new_or_changed(record['고유키'], record):
                            batch_data.append(record)

                    if batch_data:
                        self.log(f"✅ {len(batch_data)}건 전송")
                        enhanced = self.smart_engine.process_batch(batch_data)
                        self.processor.send_to_gas(enhanced)
                    
                    self.state.save_checkpoint(current_page + 1)
                    
                    # 다음 페이지 이동
                    if current_page % 10 == 0:
                        btn = self.page.locator('button.next:has(span:text-is("다음그룹"))')
                    else:
                        btn = self.page.locator(f'ul.paging button.num:has(span:text-is("{current_page + 1}"))')
                    
                    if btn.is_visible():
                        # [변경] 페이지 이동 버튼도 사람처럼 클릭
                        self._human_click(btn)
                        
                        try:
                            self.page.wait_for_function(
                                f"document.querySelector('div.result-txt-wrap button span')?.innerText.trim() !== '{first_comp}'",
                                timeout=15000 # 타임아웃 약간 여유있게 증가
                            )
                        except: pass
                        current_page += 1
                        
                        # [중요] 페이지 이동 후 랜덤 휴식 (연속 요청 방지)
                        # 너무 짧으면(1초 미만) 세션이 끊길 수 있음
                        time.sleep(random.uniform(2.0, 4.0)) 
                    else:
                        self.log("다음 페이지 없음. 종료.")
                        break

            except Exception as e:
                self.log(f"에러: {e}")
                import traceback
                traceback.print_exc()