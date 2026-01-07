import logging
import json
from bs4 import BeautifulSoup
from utils.smart_extractor import SmartExtractor

class BaseStrategy:
    def extract(self, content, rules):
        raise NotImplementedError

class JsonStrategy(BaseStrategy):
    """API 응답(JSON) 처리"""
    def extract(self, content, rules):
        if isinstance(content, str):
            try:
                data = json.loads(content)
            except:
                data = {}
        else:
            data = content

        # 리스트가 위치한 경로 탐색 (예: "response.body.items")
        if 'base_path' in rules:
            for key in rules['base_path'].split('.'):
                if isinstance(data, dict):
                    data = data.get(key, [])
                else:
                    break
        
        # 리스트가 아니면 단일 아이템으로 간주하고 리스트로 포장
        items = data if isinstance(data, list) else [data]
        
        results = []
        for item in items:
            if not isinstance(item, dict): continue
            
            record = {}
            for field_name, key_path in rules.get('fields', {}).items():
                record[field_name] = self._get_value_by_path(item, key_path)
            
            if record: results.append(record)
            
        return results

    def _get_value_by_path(self, item, path):
        val = item
        for key in path.split('.'):
            if isinstance(val, dict):
                val = val.get(key)
            else:
                return ""
        return val if val else ""

class CssStrategy(BaseStrategy):
    """HTML 파싱 및 스마트 추출"""
    def __init__(self):
        self.smart_extractor = SmartExtractor()
        self.logger = logging.getLogger("CssStrategy")

    def extract(self, content, rules):
        soup = BeautifulSoup(content, 'html.parser')
        
        # 리스트 영역 선택
        base_selector = rules.get('base_selector', 'body')
        elements = soup.select(base_selector)
        
        results = []
        for el in elements:
            record = {}
            
            # 1. 명시적 필드 추출 (CSS Selector)
            for field, selector_str in rules.get('fields', {}).items():
                if ' > ' in selector_str:
                    selector, attr = selector_str.rsplit(' > ', 1)
                else:
                    selector, attr = selector_str, 'text'
                
                if selector == 'self':
                    target = el
                else:
                    target = el.select_one(selector)
                
                if target:
                    if attr == 'text':
                        val = target.get_text(strip=True)
                    elif attr == 'inner_html': # 스마트 추출용
                        val = str(target)
                    else:
                        val = target.get(attr, '')
                    record[field] = val
                else:
                    record[field] = ""

            # 2. Smart Extraction (전화번호, 이메일 자동 탐지)
            # 설정에 "smart_extraction": true 가 있거나 특정 필드 지정 시 작동
            if rules.get('smart_extraction'):
                # 요소 전체 HTML을 텍스트로 변환하여 연락처 탐색
                full_text = str(el)
                smart_data = self.smart_extractor.extract_contacts(full_text)
                
                # 기존 데이터에 덮어쓰지 않고 비어있는 경우에만 채움 (또는 병합)
                for k, v in smart_data.items():
                    if k not in record or not record[k]:
                        record[k] = v
            
            if any(record.values()): # 빈 깡통이 아니면 추가
                results.append(record)
                
        return results

class StrategyFactory:
    @staticmethod
    def get(strategy_type):
        if strategy_type == 'json': return JsonStrategy()
        if strategy_type == 'css': return CssStrategy()
        # 필요 시 RegexStrategy, XmlStrategy 추가 가능
        raise ValueError(f"Unknown strategy type: {strategy_type}")