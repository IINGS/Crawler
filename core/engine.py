import asyncio
import logging
import json
import random
import copy
from urllib.parse import urlparse

from .network import AsyncFetcher
from .strategies import StrategyFactory
from .hooks import HookManager
from utils.data_processor import DataProcessor
from utils.state_manager import StateManager
from utils.smart_extractor import SmartExtractor

class GenericAsyncCrawler:
    def __init__(self, config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
            
        self.name = self.config.get('name', 'Unknown')
        self.domain_group = self.config.get('domain_group', 'default')
        
        self.logger = logging.getLogger(f"Crawler_{self.name}")
        
        self.fetcher = AsyncFetcher(f"Fetcher_{self.name}")
        self.processor = DataProcessor(source_name=self.name)
        self.state_manager = StateManager(self.domain_group)
        self.hook_manager = HookManager(self.config.get('hooks_file'))
        self.extractor = SmartExtractor()
        self.concurrency = self.config.get('concurrency', 3)
        self.semaphore = asyncio.Semaphore(self.concurrency)

    async def run(self):
        self.logger.info(f"🚀 Start Crawling: {self.name} (Max {self.concurrency} threads)")
        
        try:
            await self.hook_manager.run("on_start", self.fetcher)
            
            tasks = []
            req_config = self.config['request']
            pagination = req_config.get('pagination', {})
            
            if pagination:
                start = pagination.get('start', 1)
                end = pagination.get('max_page', 10)
                step = pagination.get('step', 1)

                checkpoint_key = f"{self.name}_last_page"
                last_page = await self.state_manager.get_checkpoint(checkpoint_key)

                if last_page:
                    start = int(last_page)
                    self.logger.info(f"🔄 이어하기 감지: {start}페이지부터 다시 시작합니다. (Last: {last_page})")

                if start > end:
                     self.logger.info(f"✨ 이미 모든 페이지({end}) 수집이 완료되었습니다.")
                     return
                
                for page in range(start, end + 1, step):
                    tasks.append(self.process_page(page))
            else:
                tasks.append(self.process_page(1))

            await asyncio.gather(*tasks)
            
        except Exception as e:
            self.logger.error(f"Critical Error in {self.name}: {e}")
        finally:
            await self.processor.flush()
            await self.fetcher.close()
            await self.hook_manager.run("on_finish")
            self.logger.info(f"🏁 Finished Crawling: {self.name}")

    async def process_page(self, page_num):
        async with self.semaphore:
            try:
                req_params = copy.deepcopy(self.config['request'])
                
                target_url = req_params['url'].replace('{page}', str(page_num))
                req_params['url'] = target_url
                
                if 'data' in req_params and isinstance(req_params['data'], dict):
                    for k, v in req_params['data'].items():
                        if isinstance(v, str):
                            req_params['data'][k] = v.replace('{page}', str(page_num))
                
                if 'params' in req_params:
                     pg_key = self.config['request'].get('pagination', {}).get('param')
                     if pg_key:
                         req_params['params'][pg_key] = page_num

                req_params = await self.hook_manager.run("before_request", req_params, page_num)
                if not req_params: return

                self.logger.debug(f"Fetching page {page_num}...")
                content = await self.fetcher.fetch(self.config['type'], req_params)
                
                strategy_name = self.config['extraction'].get('strategy', 'css')
                strategy = StrategyFactory.get(strategy_name)
                extracted_items = strategy.extract(content, self.config['extraction'])
                
                new_count = 0
                duplicate_count = 0

                for item in extracted_items:
                    item = await self.hook_manager.run("before_save", item)
                    if not item: continue

                    if await self.state_manager.is_new(item):
                        if self.config.get('deep_crawl', False) and item.get('홈페이지'):
                            loop = asyncio.get_running_loop()
                            item = await self.extractor.process_company(item)
                        new_count += 1
                        await self.processor.process(item)
                    else:
                        duplicate_count += 1
                
                first_item_check = ""
                if extracted_items:
                    first_item_name = extracted_items[0].get('기업명', 'Unknown')
                    first_item_check = f" (First: {first_item_name})"

                self.logger.info(f"Page {page_num}: Extracted {len(extracted_items)} items. {new_count} new, {duplicate_count} skipped.{first_item_check}")

                checkpoint_key = f"{self.name}_last_page"
                await self.state_manager.save_checkpoint(checkpoint_key, page_num)

                await asyncio.sleep(random.uniform(0.5, 1.5))

            except Exception as e:
                self.logger.error(f"Error on page {page_num}: {e}")
                await self.hook_manager.run("on_error", e, page_num)