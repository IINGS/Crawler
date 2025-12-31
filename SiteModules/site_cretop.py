# SiteModules/site_cretop.py
import time
import random
from bs4 import BeautifulSoup
from patchright.sync_api import sync_playwright 
from crawler_base import BaseCrawler

class CretopCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("cretop_com", "크레탑")
        self.start_url = "https://www.cretop.com/ET/SS/ETSS070M1"
        self.browser = None
        self.page = None

    def _init_browser(self, p):
        self.log("브라우저 초기화 (로컬 Chrome)...")
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

            self.page.on("dialog", lambda dialog: self._handle_dialog(dialog))
            self.page.on("close", lambda: self.log("❌ [SYSTEM] 페이지 닫힘"))
            self.page.on("crash", lambda: self.log("💥 [SYSTEM] 브라우저 충돌"))
            self.page.on("pageerror", lambda err: self.log(f"💀 [JS ERROR] {err}"))

        except Exception as e:
            self.log(f"초기화 에러: {e}")
            raise e

    def _handle_dialog(self, dialog):
        try:
            msg = dialog.message
            self.log(f"📢 [팝업 감지] 내용: {msg}")
            dialog.accept()
        except: pass

    def _human_click(self, locator):
        try:
            locator.wait_for(state="visible", timeout=5000)
            box = locator.bounding_box()
            if not box:
                locator.click(force=True)
                time.sleep(1.0)
                return

            target_x = box['x'] + box['width'] / 2 + random.uniform(-3, 3)
            target_y = box['y'] + box['height'] / 2 + random.uniform(-3, 3)

            self.page.mouse.move(target_x, target_y, steps=random.randint(10, 25))
            time.sleep(random.uniform(0.5, 1.0))
            self.page.mouse.click(target_x, target_y)
            time.sleep(random.uniform(1.5, 2.5))
            
        except:
            locator.click(force=True)
            time.sleep(1.0)

    def _setup_search_conditions(self):
        target_url = "https://www.cretop.com/ET/SS/ETSS070M1"
        self.log(f"접속: {target_url}")
        
        try:
            self.page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
            self.page.wait_for_load_state("networkidle")
            time.sleep(3.0)
        except: pass

        login_check_xpath = "xpath=//*[contains(text(), '정상')]"
        try:
            self.page.locator(login_check_xpath).first.wait_for(state="attached", timeout=5000)
        except:
            self.log("📢 [60초 대기] 로그인 필요.")
            try:
                self.page.locator(login_check_xpath).first.wait_for(state="attached", timeout=60000)
                time.sleep(3.0)
            except:
                return False

        # 체크박스
        target_labels = ["정상", "소기업", "개인사업자"]
        for label_text in target_labels:
            try:
                xpath = f"xpath=(//*[contains(text(), '{label_text}')])[last()]/preceding::input[@type='checkbox'][1]"
                el = self.page.locator(xpath)
                if el.count() == 0:
                    xpath = f"xpath=(//*[contains(text(), '{label_text}')])[1]/preceding::input[@type='checkbox'][1]"
                    el = self.page.locator(xpath)
                
                if el.count() > 0 and not el.is_checked():
                    self._human_click(el)
                    self.log(f"Checking [{label_text}]")
                    time.sleep(1.0)
            except: pass

        # 조회 버튼
        self.log("조회 버튼 클릭 (5초 대기)...")
        try:
            time.sleep(2.0)
            search_btn = self.page.locator("xpath=//button[contains(., '조회하기')]")
            if search_btn.count() > 0:
                self._human_click(search_btn)
                self.page.wait_for_load_state("networkidle")
                self.log("  - 결과 로딩 중... (안전하게 5초 대기)")
                time.sleep(5.0) 
                try:
                    self.page.wait_for_selector("div.result-txt-wrap", state="attached", timeout=30000) # 타임아웃 30초로 증가
                    self.log("  ✅ 결과 리스트 포착됨")
                except:
                    self.log("  ⚠️ 결과 리스트 늦음/없음")
                time.sleep(2.0) 
            else:
                return False
        except: return False

        # 100개 보기
        try:
            self.log("100개 보기 설정 (천천히)...")
            time.sleep(2.0)
            select_box = self.page.locator('#pageCount')
            select_box.wait_for(state="visible", timeout=5000)
            select_box.scroll_into_view_if_needed()
            self._human_click(select_box)
            time.sleep(2.0)
            for _ in range(3):
                self.page.keyboard.press("ArrowDown")
                time.sleep(0.5)
            self.page.keyboard.press("Enter")
            self.page.wait_for_load_state("networkidle")
            self.log("  - 리스트 갱신 대기 (5초)...")
            time.sleep(5.0)
            try:
                self.page.wait_for_function("document.querySelectorAll('div.result-txt-wrap').length > 15", timeout=10000)
                self.log("  ✅ 100개 리스트 갱신 확인됨")
            except: pass
            return True
        except: return True

    def _get_current_page_num(self):
        try:
            el = self.page.locator("ul.paging button.num.on span").first
            if el.is_visible():
                return int(el.inner_text().strip())
            return 1
        except: return 1

    def _get_value_by_title(self, item, title):
        try:
            span = item.find('span', class_='list-tit', string=title)
            return "".join([s.get_text(strip=True) for s in span.find_next_siblings('span', class_='list-info')]) if span else ""
        except: return ""

    def _navigate_to_checkpoint(self, target_page):
        if target_page <= 1: return
        self.log(f"🚀 {target_page}페이지로 복구 이동 시작 (천천히)...")
        
        while True:
            current_page = self._get_current_page_num()
            current_group_end = ((current_page - 1) // 10 + 1) * 10
            
            if target_page > current_group_end:
                self.log(f"  - 그룹 이동...")
                next_group_btn = self.page.locator('button.next:has(span:text-is("다음그룹"))')
                if next_group_btn.is_visible():
                    time.sleep(1.5)
                    next_group_btn.click(force=True)
                    self.page.wait_for_load_state("networkidle")
                    time.sleep(3.0)
                else:
                    self.log("  ⚠️ 다음 그룹 버튼 없음.")
                    break
            else:
                break
        
        current_page = self._get_current_page_num()
        if current_page != target_page:
            self.log(f"  - 상세 페이지 점프...")
            try:
                buttons = self.page.locator("ul.paging button.num")
                count = buttons.count()
                for i in range(count):
                    btn = buttons.nth(i)
                    if btn.inner_text().strip() == str(target_page):
                        time.sleep(1.0)
                        btn.click(force=True)
                        self.page.wait_for_load_state("networkidle")
                        try:
                            self.page.wait_for_function(
                                f"document.querySelector('ul.paging button.num.on span')?.innerText == '{target_page}'",
                                timeout=10000
                            )
                        except: pass
                        time.sleep(3.0)
                        break
            except: pass

    def run(self):
        self.log("시작...")
        with sync_playwright() as p:
            self._init_browser(p)
            try:
                if not self._setup_search_conditions():
                    self.log("설정 실패. 종료")
                    return

                saved_page = self.state.load_checkpoint()
                start_page = saved_page if saved_page > 0 else 1
                
                if start_page > 1: 
                    self._navigate_to_checkpoint(start_page)
                
                real_current = self._get_current_page_num()
                if real_current != start_page:
                    start_page = real_current

                current_page = start_page
                
                while True:
                    self.log(f"▶ {current_page} 페이지 처리")
                    if self.page.is_closed(): break
                    
                    time.sleep(2.0)
                    
                    # [핵심 수정] 데이터가 뜰 때까지 3번 재시도 (끈질기게 기다림)
                    items = []
                    for attempt in range(3):
                        try: 
                            self.page.wait_for_selector('div.result-txt-wrap', timeout=20000) # 20초 대기
                            if self.page.locator('div.result-txt-wrap').count() < 5:
                                time.sleep(3.0)
                        except: pass

                        soup = BeautifulSoup(self.page.content(), 'html.parser')
                        items = soup.select('div.result-txt-wrap')
                        
                        if items:
                            break # 찾았으면 탈출
                        else:
                            self.log(f"⚠️ 데이터 감지 안됨. 재확인 중... ({attempt+1}/3)")
                            
                            # 혹시 '페이지 만료' 텍스트가 있는지 확인
                            body_text = soup.get_text()
                            if "만료" in body_text or "로그인" in body_text:
                                self.log("🚨 [페이지 만료] 감지됨! 봇을 종료합니다. (현재 페이지 저장 안함)")
                                return # 종료해서 다음 실행 때 재시도하도록 유도
                                
                            time.sleep(5.0) # 5초 후 재시도

                    if not items:
                        self.log("❌ 3회 재시도 실패. 데이터 없음. 종료.")
                        break

                    first_comp = ""
                    batch_data = []
                    
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
                        self.log(f"✅ {len(batch_data)}건 추출 -> GAS 전송")
                        enhanced = self.smart_engine.process_batch(batch_data)
                        self.processor.send_to_gas(enhanced)
                    else:
                        self.log("Skip (변동없음)")
                    
                    self.state.save_checkpoint(current_page + 1)
                    
                    # --- 페이지 이동 ---
                    next_page_num = current_page + 1
                    is_next_group = (current_page % 10 == 0)

                    time.sleep(random.uniform(2.0, 4.0))

                    btn = None
                    if is_next_group:
                        btn = self.page.locator('button.next:has(span:text-is("다음그룹"))')
                    else:
                        btn = self.page.locator(f"ul.paging button.num").filter(has_text=str(next_page_num))
                        if btn.count() > 1:
                            for i in range(btn.count()):
                                if btn.nth(i).inner_text().strip() == str(next_page_num):
                                    btn = btn.nth(i)
                                    break
                    
                    if btn and btn.count() > 0 and btn.is_visible():
                        self.log(f"다음 페이지({next_page_num}) 이동...")
                        time.sleep(1.0)
                        btn.click(force=True)
                        
                        try:
                            js_check = f"() => document.querySelector('div.result-txt-wrap button span')?.innerText.trim() !== `{first_comp}`"
                            self.page.wait_for_function(js_check, timeout=15000)
                            current_page += 1
                            time.sleep(random.uniform(2.0, 3.0))
                        except:
                            self.log(f"❌ {next_page_num}페이지 로딩 실패")
                            try:
                                time.sleep(5.0)
                                btn.click(force=True)
                                time.sleep(5.0)
                                current_page += 1
                            except: break
                    else:
                        self.log("다음 페이지 버튼 없음. 종료.")
                        break

            except Exception as e:
                self.log(f"에러: {e}")