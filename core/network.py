import asyncio
import aiohttp
import logging
import random
import json
import copy

try:
    from patchright.async_api import async_playwright
    USING_PATCHRIGHT = True
except ImportError:
    from playwright.async_api import async_playwright
    USING_PATCHRIGHT = False

from config import USER_AGENTS, BROWSER_CONFIG, DEFAULT_HEADERS

class AsyncFetcher:
    def __init__(self, context_name="Fetcher"):
        self.logger = logging.getLogger(context_name)
        self.playwright = None
        self.browser = None
        self.context = None
        self.http_session = None
        
        if USING_PATCHRIGHT:
            self.logger.info("🛡️ Anti-Bot Engine: Patchright (Detected & Active)")
        else:
            self.logger.warning("⚠️ Anti-Bot Engine: Standard Playwright (Patchright not found)")

    def _get_headers(self):
        headers = DEFAULT_HEADERS.copy()
        headers["User-Agent"] = random.choice(USER_AGENTS)
        return headers

    async def _get_http_session(self):
        if self.http_session is None or self.http_session.closed:
            self.http_session = aiohttp.ClientSession()
        return self.http_session

    async def fetch(self, type, req_config):
        if type in ['api', 'html']:
            return await self._fetch_http(req_config)
        elif type == 'browser':
            return await self._fetch_browser(req_config)
        else:
            raise ValueError(f"Unknown fetch type: {type}")

    async def _fetch_http(self, config):
        method = config.get('method', 'GET')
        url = config['url']
        params = config.get('params')
        data = config.get('data')
        
        session = await self._get_http_session()
        
        async with session.request(
            method, 
            url, 
            params=params, 
            data=data,
            json=config.get('json'),
            headers=self._get_headers()
        ) as response:
            response.raise_for_status()
            if 'application/json' in response.headers.get('Content-Type', ''):
                return await response.json()
            return await response.text()

    async def _fetch_browser(self, config):
        await self._ensure_browser()
        
        page = await self.context.new_page()
        await page.set_viewport_size({"width": 1920, "height": 1080})
        page.on("dialog", lambda dialog: dialog.accept())
        try:
            self.logger.debug(f"Browsing: {config['url']}")
            await page.goto(config['url'], wait_until='networkidle', timeout=60000)
            
            if 'actions' in config:
                for action in config['actions']:
                    act_type = action.get('type')
                    selector = action.get('selector')
                    
                    if act_type == 'wait':
                        await page.wait_for_selector(selector, state='visible', timeout=10000)
                    elif act_type == 'click':
                        await asyncio.sleep(random.uniform(0.1, 0.3))
                        await page.click(selector, delay=random.randint(100, 300))
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                    elif act_type == 'sleep':
                        await asyncio.sleep(action.get('seconds', 1))
                    elif act_type == 'input':
                        await page.fill(selector, action.get('value'))
                    elif act_type == 'press':
                        key = action.get('key')
                        await page.keyboard.press(key)
                        await asyncio.sleep(random.uniform(0.2,0.5))
                    elif act_type == 'mouse_move':
                        try:
                            element = await page.wait_for_selector(selector, state='visible', timeout=5000)
                            box = await element.bounding_box()
                            
                            if box:
                                target_x = box['x'] + box['width'] / 2 + random.uniform(-5, 5)
                                target_y = box['y'] + box['height'] / 2 + random.uniform(-5, 5)
                                
                                await page.mouse.move(target_x, target_y, steps=random.randint(30, 60))
                        except Exception as e:
                            self.logger.warning(f"Mouse move failed: {e}")
                    elif act_type == 'hover':
                        try:
                            await page.hover(selector)
                            await asyncio.sleep(random.uniform(0.3, 0.8))
                        except Exception:
                            pass
            
            content = await page.content()
            return content
            
        except Exception as e:
            self.logger.error(f"Browser Fetch Error: {e}")
            raise
        finally:
            await page.close()

    async def _ensure_browser(self):
        if not self.playwright:
            self.playwright = await async_playwright().start()
            
            launch_args = copy.deepcopy(BROWSER_CONFIG)
            
            if USING_PATCHRIGHT:
                # Patchright 사용 시: channel 설정이 있으면 강제로 제거 (자체 바이너리 사용 유도)
                if "channel" in launch_args:
                    self.logger.info("🔧 Config Correction: Removing 'channel' setting to use Patchright's bundled binary.")
                    del launch_args["channel"]

                # args 병합 (중복 방지 로직)
                current_args = set(launch_args.get('args', []))
                required_args = {
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox"
                }
                # 합집합으로 병합 후 다시 리스트로 변환
                launch_args['args'] = list(current_args | required_args)

            self.browser = await self.playwright.chromium.launch(**launch_args)
            
            # Context 생성
            self.context = await self.browser.new_context(
                viewport=None,  # 윈도우 크기에 맞춤
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                device_scale_factor=1,
                # Patchright 사용 시 navigator.webdriver는 자동 처리되므로 스크립트 최소화
            )
            
            # Playwright일 때만 수동 우회 스크립트 주입 (Patchright는 내부 처리됨)
            if not USING_PATCHRIGHT:
                await self.context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """)

    async def close(self):
        if self.http_session: await self.http_session.close()
        if self.context: await self.context.close()
        if self.browser: await self.browser.close()
        if self.playwright: await self.playwright.stop()