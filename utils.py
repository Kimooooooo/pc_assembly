# utils.py
import re
from serpapi import Client
import config

SERPAPI_KEY = config.SERPAPI_KEY

def parse_keywords(llm_response):
    """
    LLM 응답에서 [카테고리_등급] 태그를 찾아 키워드를 추출합니다.
    반환값 예시: {'CPU': ['i3 12100', 'i5 13400', 'i7 14700'], ...}
    """
    keywords = {}
    categories = ["CPU", "GPU", "MAINBORD", "RAM", "POWER", "CASE", "SSD", "COOLER"]
    tiers = ["LOW", "MID", "HIGH"]

    for category in categories:
        keywords[category] = []
        for tier in tiers:
            # 예: [CPU_LOW], [CPU_MID] ... 태그 찾기
            tag = f"{category}_{tier}"
            pattern = rf'\[{tag}\]\s*(.+?)(?=\n\[|$)'
            match = re.search(pattern, llm_response, re.DOTALL)
            
            if match:
                kw = match.group(1).strip()
                if kw and '없음' not in kw:
                    keywords[category].append(kw)
        
        # 만약 파싱된 게 하나도 없으면 기본값(카테고리명)이라도 넣어서 검색되게 함
        if not keywords[category]:
            keywords[category] = [category]

    return keywords

def parse_unknown_items(text):
    """[모르는 항목] 섹션 파싱"""
    unknown = []
    if "[모르는 항목]" in text:
        try:
            section = text.split("[모르는 항목]")[1].split("[")[0]
            for line in section.split('\n'):
                line = line.strip()
                if line.startswith('-'):
                    unknown.append(line[1:].strip())
        except:
            pass
    return unknown

def web_search(query):
    """웹 검색 (SerpAPI)"""
    try:
        if not SERPAPI_KEY: return ""
        client = Client(api_key=SERPAPI_KEY)
        results = client.search({
            'q': query,
            'engine': 'google',
            'num': 3,
            'hl': 'ko',
            'gl': 'kr'
        })
        snippets = [r.get('snippet', '') for r in results.get('organic_results', [])]
        return '\n'.join(snippets) if snippets else ""
    except Exception:
        return ""

def format_search_results(results):
    return str(results)[:1000]