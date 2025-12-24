# main.py
import pkgutil
import importlib
import inspect
import SiteModules
from concurrent.futures import ThreadPoolExecutor
import time

def run_crawlers_in_group(group_name, crawler_list):
    """
    하나의 그룹 안에 있는 크롤러들을 '순서대로' 실행합니다.
    (같은 도메인 충돌 방지)
    """
    print(f"■ [그룹 시작] '{group_name}' 그룹 실행 (대기열: {len(crawler_list)}개)")
    
    for crawler in crawler_list:
        try:
            print(f"  ▶ {crawler.__class__.__name__} 실행 중...")
            crawler.run()
        except Exception as e:
            print(f"  !! [개별 에러] {crawler.__class__.__name__}: {e}")
            
    print(f"■ [그룹 종료] '{group_name}' 완료.\n")

def main():
    print(">>> [시스템] 크롤러 자동 감지 및 그룹 병렬 처리 시작...\n")

    # 1. 모든 크롤러 인스턴스 수집 및 그룹핑
    crawlers_by_group = {} # {"smes_gov": [crawler1, crawler2], "innobiz": [crawler3]}

    package = SiteModules
    prefix = package.__name__ + "."

    for _, name, _ in pkgutil.iter_modules(package.__path__, prefix):
        if name == "SiteModules.common" or name == "SiteModules.__init__":
            continue

        try:
            module = importlib.import_module(name)
            
            for member_name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and member_name.endswith('Crawler'):
                    if obj.__module__ == name:
                        # 인스턴스 생성
                        instance = obj()
                        
                        # 그룹명 확인 (없으면 그냥 자기 이름으로 독립 그룹)
                        group = getattr(instance, 'group_name', member_name)
                        
                        if group not in crawlers_by_group:
                            crawlers_by_group[group] = []
                        crawlers_by_group[group].append(instance)
                        
        except Exception as e:
            print(f"!! [오류] {name} 모듈 로드 실패: {e}")

    # 2. 수집된 그룹 확인
    total_groups = len(crawlers_by_group)
    print(f">>> 총 {total_groups}개의 도메인 그룹을 발견했습니다.")
    for grp, lst in crawlers_by_group.items():
        print(f"   - [{grp}] : {[c.__class__.__name__ for c in lst]}")
    print("-" * 60)

    # 3. 그룹별 병렬 실행 (최대 5개 그룹 동시 실행)
    # max_workers=5 : 동시에 접속할 서로 다른 도메인 개수
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for group_name, crawler_list in crawlers_by_group.items():
            # 각 그룹(리스트)을 별도의 스레드에게 맡김
            futures.append(executor.submit(run_crawlers_in_group, group_name, crawler_list))
        
        # 모든 작업이 끝날 때까지 대기
        for future in futures:
            future.result()

    print(">>> [시스템] 모든 병렬 크롤링 작업 완료")

if __name__ == "__main__":
    main()