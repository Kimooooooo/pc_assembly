# utils.py

"""
유틸리티 함수 모음
"""

import re
from serpapi import Client
import os
import config

SERPAPI_KEY = 'key'

def parse_keywords(llm_response):
    keywords = {}
    categories = ["CPU", "GPU", "MAINBORD", "RAM", "POWER", "CASE", "SSD","HDD", "COOLER"]

    for category in categories:
        pattern = rf'\[{category} 검색 키워드\]\s*\n(.+?)(?=\n\[|$)'
        match = re.search(pattern, llm_response, re.DOTALL)
        
        if match:
            keyword = match.group(1).strip()
            keywords[category] = keyword if keyword != '없음' else ''
        else:
            keywords[category] = category
    
    return keywords


def parse_unknown_items(llm_response):
    """
    LLM 응답에서 모르는 게임/프로그램 추출
    
    Args:
        llm_response: LLM의 텍스트 응답
    
    Returns:
        ["GTA 6", "언리얼 엔진 5.4", ...]
    """
    pattern = r'\[모르는 항목\]\s*\n(.+?)(?=\n\[|$)'
    match = re.search(pattern, llm_response, re.DOTALL)
    
    if match:
        items = re.findall(r'- (.+?)(?:\(|$)', match.group(1))
        return [item.strip() for item in items]
    
    return []

num_results = 3
def web_search(query):
    try:
        params = {
            'q': query,
            'api_key': SERPAPI_KEY,
            'engine': 'google',
            'num': num_results,
            'location' : 'South Korea',
            'google_domain' : 'google.co.kr',
            'gl' : 'kr'
        }
        
        client = Client(params = params)
        results = client.get_dict()
        
        snippets = []
        if 'organic_results' in results:
            for result in results['organic_results'][:num_results]:
                snippets.append(result.get('snippet', ''))
        
        if snippets:
            return '\n'.join(snippets)
        else:
            return '검색 결과를 찾을 수 없습니다.'
    
    except Exception as e:
        error_msg = str(e)
        if 'quota' in error_msg.lower() or 'limit' in error_msg.lower():
            return '웹 검색 한도 초과(100회). 직접 입력해주세요.'
        else:
            return f'검색 중 오류 발생. 권장 사양 입력 필요: {error_msg}'


def format_search_results(search_dict):
    """
    검색 결과 딕셔너리를 텍스트로 포맷팅
    
    Args:
        search_dict: {"GTA 6": "검색결과...", ...}
    
    Returns:
        포맷팅된 문자열
    """
    result = ""
    for item, content in search_dict.items():
        result += f"\n[{item} 권장 사양]\n{content}\n"
    return result