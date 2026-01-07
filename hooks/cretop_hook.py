from bs4 import BeautifulSoup
import logging

logger = logging.getLogger("Hook-Cretop")

def _get_value_by_title(soup_item, title):
    """
    레거시 코드의 _get_value_by_title 로직 이식
    특정 타이틀(예: '대표자명')을 가진 span을 찾고, 그 형제 요소들의 텍스트를 반환
    """
    try:
        span = soup_item.find('span', class_='list-tit', string=title)
        if span:
            siblings = span.find_next_siblings('span', class_='list-info')
            return "".join([s.get_text(strip=True) for s in siblings])
        return ""
    except Exception:
        return ""

async def before_save(item):
    """
    Extraction 단계에서 가져온 '_raw_html'을 파싱하여
    대표자명, 기업유형 등 상세 정보를 추출하여 item에 병합함.
    """
    raw_html = item.get('_raw_html', '')
    
    if raw_html:
        try:
            # HTML 조각 파싱
            soup = BeautifulSoup(raw_html, 'html.parser')
            
            # 상세 정보 추출 및 매핑
            item['대표자명'] = _get_value_by_title(soup, "대표자명")
            item['기업유형'] = _get_value_by_title(soup, "기업유형/형태")
            item['사업자번호'] = _get_value_by_title(soup, "사업자번호")
            item['산업분류'] = _get_value_by_title(soup, "산업분류")
            item['주소'] = _get_value_by_title(soup, "주소")
            
        except Exception as e:
            logger.error(f"Error parsing detail info: {e}")

    # 임시 필드 삭제
    if '_raw_html' in item:
        del item['_raw_html']

    return item