"""
[Hook 파일 작성 가이드]
필요한 함수만 구현하면 됩니다. 구현하지 않은 함수는 엔진이 알아서 무시합니다.
모든 함수는 비동기(async)로 작성되어야 합니다.
"""

import logging

# 로거 설정 (선택 사항)
logger = logging.getLogger("MyHook")

async def on_start(fetcher):
    """
    [수집 시작 전 1회 실행]
    주로 로그인 처리나 초기 세션 설정에 사용됩니다.
    
    :param fetcher: network.AsyncFetcher 인스턴스 (브라우저/세션 제어 가능)
    """
    # 예: 브라우저로 로그인 페이지 이동 후 로그인 수행
    # await fetcher.fetch('browser', {'url': '...', 'actions': [...]})
    pass

async def before_request(req_params, page_num):
    """
    [매 페이지 요청 직전 실행]
    URL, 파라미터, 헤더 등을 동적으로 수정할 때 사용합니다.
    
    :param req_params: JSON 설정의 'request' 딕셔너리 복사본
    :param page_num: 현재 수집하려는 페이지 번호
    :return: 수정된 req_params (None을 리턴하면 해당 페이지 요청을 건너뜀)
    """
    # 예: URL에 오늘 날짜 추가
    # req_params['params']['date'] = datetime.now().strftime('%Y%m%d')
    return req_params

async def before_save(item):
    """
    [데이터 추출 후 저장 직전 실행]
    데이터 정제, 포맷팅, 필터링(저장 거부)을 수행합니다.
    
    :param item: 추출된 데이터 딕셔너리 (예: {'기업명': '...', ...})
    :return: 수정된 item (None을 리턴하면 이 데이터는 저장하지 않음)
    """
    # 예: 금액에서 '원' 제거 및 숫자 변환
    # if '매출액' in item:
    #     item['매출액'] = item['매출액'].replace('원', '').replace(',', '')
    
    # 예: 특정 조건 데이터 필터링 (저장 안 함)
    # if item.get('상태') == '폐업':
    #     return None
        
    return item

async def on_error(error, page_num):
    """
    [에러 발생 시 실행]
    """
    logger.error(f"{page_num}페이지에서 에러 발생: {error}")

async def on_finish():
    """
    [모든 수집 종료 후 1회 실행]
    리소스 정리나 알림 발송 등에 사용합니다.
    """
    pass