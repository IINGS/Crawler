import logging
import json
import re
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

        if 'base_path' in rules:
            for key in rules['base_path'].split('.'):
                if isinstance(data, dict):
                    data = data.get(key, [])
                else:
                    break
        
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
        
        base_selector = rules.get('base_selector', 'body')
        elements = soup.select(base_selector)
        
        results = []
        for el in elements:
            record = {}
            
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
                    elif attr == 'inner_html':
                        val = str(target)
                    else:
                        val = target.get(attr, '')
                    record[field] = val
                else:
                    record[field] = ""

            if rules.get('smart_extraction'):
                full_text = str(el)
                smart_data = self.smart_extractor.extract_contacts(full_text)
                
                for k, v in smart_data.items():
                    if k not in record or not record[k]:
                        record[k] = v
            
            if any(record.values()):
                results.append(record)
                
        return results

class RegexStrategy(BaseStrategy):
    """정규표현식 기반 추출"""
    def extract(self, content, rules):
        base_pattern = rules.get('base_pattern', '')
        if not base_pattern: return []

        results = []
        for match in re.finditer(base_pattern, content, re.DOTALL):
            item_text = match.group(0)
            match_groups = match.groupdict()
            record = {}
            
            for field, pattern in rules.get('fields', {}).items():
                val = ""
                if pattern in match_groups:
                    val = match_groups[pattern]
                
                elif isinstance(pattern, str) and pattern.isdigit():
                    try:
                        val = match.group(int(pattern))
                    except IndexError:
                        pass
                else:
                    sub_match = re.search(pattern, item_text, re.DOTALL)
                    if sub_match:
                        val = sub_match.group(1) if sub_match.groups() else sub_match.group(0)
                
                record[field] = val if val else ""
            
            if any(record.values()):
                results.append(record)
        return results

class XmlStrategy(CssStrategy):
    """XML 파싱 전략 (BeautifulSoup 'xml' 파서 사용)"""
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger("XmlStrategy")
        
    def extract(self, content, rules):
        try:
            soup = BeautifulSoup(content, 'xml')
        except Exception:
            soup = BeautifulSoup(content, 'html.parser')
            
        base_selector = rules.get('base_selector', '')
        elements = soup.select(base_selector) if base_selector else [soup]
        
        results = []
        for el in elements:
            record = {}
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
                    elif attr == 'inner_html':
                        val = str(target)
                    else:
                        val = target.get(attr, '')
                    record[field] = val
                else:
                    record[field] = ""
            
            if rules.get('smart_extraction'):
                full_text = str(el)
                smart_data = self.smart_extractor.extract_contacts(full_text)
                
                for k, v in smart_data.items():
                    if k not in record or not record[k]:
                        record[k] = v

            if any(record.values()):
                results.append(record)
        return results
class StrategyFactory:
    @staticmethod
    def get(strategy_type):
        if strategy_type == 'json': return JsonStrategy()
        if strategy_type == 'css': return CssStrategy()
        if strategy_type == 'regex': return RegexStrategy()
        if strategy_type == 'xml': return XmlStrategy()
        raise ValueError(f"Unknown strategy type: {strategy_type}")