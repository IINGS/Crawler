# check_block.py
from googlesearch import search
import time

print(">>> 구글 차단 여부 테스트 시작...")

test_keywords = ["삼성전자", "LG전자", "현대자동차"]

try:
    for i, keyword in enumerate(test_keywords):
        print(f"[{i+1}] '{keyword}' 검색 시도 중...", end=" ")
        
        # 검색 시도 (결과 1개만 요청)
        results = search(keyword, num_results=1, lang="ko")
        
        # 제너레이터이므로 실제로 값을 꺼내봐야 요청이 전송됨
        for url in results:
            print(f"성공! (URL: {url})")
            break
            
        time.sleep(2) # 2초 간격 테스트

    print("\n>>> 테스트 통과: 현재 IP는 차단되지 않았습니다.")

except Exception as e:
    print(f"\n\n>>> !! 차단 확인 !!")
    print(f"에러 메시지: {e}")
    if "429" in str(e):
        print("분석: 구글이 현재 귀하의 IP를 '봇'으로 인식하여 차단했습니다.")
    else:
        print("분석: 다른 네트워크/라이브러리 문제입니다.")