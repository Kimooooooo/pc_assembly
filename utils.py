# utils.py

"""
유틸리티 함수 모음
"""
import requests
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
    unknown_items = []
    
    # 1. [모르는 항목] 섹션의 내용 추출 (가장 유력한 섹션)
    # 기존 프롬프트 구조에 맞춰 [모르는 항목]을 찾습니다.
    pattern_old = r'\[모르는 항목\]\s*\n(.+?)(?=\n\[|$)'
    match = re.search(pattern_old, llm_response, re.DOTALL)
    
    if match:
        content = match.group(1)
        # ✅ 정규 표현식: 각 줄에서 하이픈(-)과 공백을 무시하고 뒤따르는 모든 텍스트를 추출
        # (이로써 '-GTA 6', '-GTA 6 - 설명' 형태 모두 대응 가능)
        items = re.findall(r'-\s*(.+)', content)
        
        for item in items:
            # 추출된 항목에서 ' - ' 이후의 설명 부분은 제거하고, 프로그램 이름만 추출
            name = item.strip().split(' - ')[0].strip()
            
            # 항목이 비어있지 않고, '없음' 같은 키워드가 아니라면 추가
            if name and name.lower() != '없음':
                unknown_items.append(name)
                
    # 2. [웹 검색 필요 항목] 섹션이 있다면 해당 섹션에서도 항목 추출 (새로운 프롬프트 지원)
    # (새 프롬프트 구조를 사용했다면 이 섹션을 우선적으로 파싱하도록 로직을 추가할 수 있습니다.)
    # (여기서는 기존 [모르는 항목] 섹션만 확실히 수정하여 당면한 오류를 해결합니다.)

    return unknown_items

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
        
        client = Client()
        results = client.search(params)
        
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