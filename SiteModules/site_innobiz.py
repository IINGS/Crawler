# SiteModules/site_innobiz.py
from bs4 import BeautifulSoup, Comment
from crawler_base import BaseCrawler

class InnobizCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("innobiz_net", "이노비즈")
        self.base_url = 'https://www.innobiz.net/company/company2_list.asp'

    def _get_homepage(self, row):
        """이노비즈 전용: 주석(Comment) 안에 숨겨진 링크 찾기"""
        comments = row.find_all(string=lambda text: isinstance(text, Comment))
        for c in comments:
            if "href" in c:
                soup = BeautifulSoup(c, 'html.parser')
                a = soup.find('a')
                if a and a.get('href'): return a.get('href').replace("http://https://", "https://")
        return ""

    def fetch_items(self, page):
        # [1] 도구 사용: URL만 던지면 soup가 나옴
        soup = self.get_soup(self.base_url, params={'Page': page})
        if not soup: return []

        rows = soup.select('table.table_list_style1 tbody tr')
        if not rows or (len(rows) == 1 and "없습니다" in rows[0].get_text()):
            return []

        items = []
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 6 or "없습니다" in row.get_text(): continue

            # [2] 데이터 추출에만 집중
            items.append({
                "기업명": cols[1].get_text(strip=True),
                "대표자명": cols[2].get_text(strip=True),
                "지역": cols[3].get_text(strip=True),
                "기술": cols[4].get_text(strip=True),
                "업종": cols[5].get_text(strip=True),
                "홈페이지": self._get_homepage(row)
            })
        return items