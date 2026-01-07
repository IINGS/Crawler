from bs4 import BeautifulSoup, Comment
import logging

logger = logging.getLogger("Hook-Innobiz")

async def before_save(item):
    """
    저장 직전에 실행됨.
    Extraction 단계에서 가져온 '_raw_html'을 분석하여
    주석(Comment) 속에 숨겨진 홈페이지 링크를 추출함.
    """
    raw_html = item.get('_raw_html', '')
    
    if raw_html:
        try:
            # BeautifulSoup으로 HTML 조각 파싱
            soup = BeautifulSoup(raw_html, 'html.parser')
            
            # 주석(Comment) 객체만 찾기
            comments = soup.find_all(string=lambda text: isinstance(text, Comment))
            
            for c in comments:
                # 주석 안에 href가 있다면 링크로 간주
                if "href" in c:
                    comment_soup = BeautifulSoup(str(c), 'html.parser')
                    a_tag = comment_soup.find('a')
                    if a_tag and a_tag.get('href'):
                        link = a_tag.get('href')
                        # http://https:// 같은 오타 수정 로직 (기존 코드 유지)
                        link = link.replace("http://https://", "https://")
                        item['홈페이지'] = link
                        break
        except Exception as e:
            logger.error(f"Error parsing hidden link: {e}")

    # 임시 필드 삭제 (DB에 저장할 필요 없음)
    if '_raw_html' in item:
        del item['_raw_html']

    return item