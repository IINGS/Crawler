import asyncio
import glob
import logging
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from core.engine import GenericAsyncCrawler
from utils.data_processor import DataProcessor

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

async def main():
    config_pattern = os.path.join("configs", "*.json")
    config_files = glob.glob(config_pattern)
    
    if not config_files:
        logging.error("❌ 설정 파일 없음")
        return

    # 1. 전역 업로드 워커 시작
    await DataProcessor.start_worker()

    try:
        crawlers = []
        for conf_path in config_files:
            try:
                crawler = GenericAsyncCrawler(conf_path)
                crawlers.append(crawler)
            except Exception as e:
                logging.error(f"Config Error {conf_path}: {e}")

        # 2. 크롤링 병렬 실행
        if crawlers:
            await asyncio.gather(*(crawler.run() for crawler in crawlers))
        
    finally:
        # 3. 크롤링 끝나면 큐에 남은 데이터 다 보낼 때까지 대기 후 종료
        await DataProcessor.stop_worker()

if __name__ == "__main__":
    try:
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("🛑 강제 종료")