import openai
from prompts import *
from compatibility import check_compatibility
from utils import parse_keywords, parse_unknown_items, web_search, format_search_results
import re 
from config import OPENAI_API_KEY

client = openai.OpenAI(api_key=OPENAI_API_KEY)


def generate_quote(budget, purpose, notes, vector_db=None):
  
    
    print("\n" + "="*70)
    print("PC 견적 생성 시작")
    print("="*70)
    
    # ===== 0단계: 게임/프로그램 인식 및 검색 =====
    print("\n[0단계] 게임/프로그램 인식 중...")
    
    # 0-A: 인식
    messages = create_recognition_messages(notes)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    
    recognition_result = response.choices[0].message.content
    print(f"인식 결과:\n{recognition_result}")
    
    # 0-B: 모르는 항목 추출
    unknown_items = parse_unknown_items(recognition_result)
    print(f'추출된 모르는 항목 :  {unknown_items}')
    
    # 0-C: 검색 필요 시 웹 검색
    search_results = ""
    if unknown_items:
        print(f"\n다음 항목의 정보를 웹에서 검색합니다: {unknown_items}")
        
        search_dict = {}
        for item in unknown_items:
            print(f"  - {item} 검색 중...")
            result = web_search(f"{item} 권장 사양 PC 요구사항")
            search_dict[item] = result
        
        search_results = format_search_results(search_dict)
        print(f"검색 완료:\n{search_results}")
        
        # 검색 결과 포함해서 키워드 생성
        messages = create_query_translation_with_search_messages(
            budget, purpose, notes, search_results
        )
    else:
        # 기본 키워드 생성
        messages = create_query_translation_messages(budget, purpose, notes)
    
    # 0-D: 키워드 생성
    print("\n[0단계] 검색 키워드 생성 중...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    
    keywords = parse_keywords(response.choices[0].message.content)
    print(f"생성된 키워드:")
    for cat, kw in keywords.items():
        print(f"  {cat}: {kw}")
    
    # ===== 1단계: 벡터DB 검색 =====
    print("\n[1단계] 벡터DB에서 부품 검색 중...")
    
    if vector_db:
        parts_top20 = {}
        for category, keyword in keywords.items():
            parts_top20[category] = vector_db.search(
                category=category.lower(),
                query=keyword,
                top_k=20
            )
    
    print(f"검색 완료: 각 카테고리별 20개씩")
    
    # ===== 2단계: LLM 필터링 =====
    print("\n[2단계] LLM 1차 필터링 중 (20개 → 5~10개)...")
    
    messages = create_filter_messages(budget, purpose, notes, parts_top20)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    
    filtered_parts = response.choices[0].message.content
    print(f"필터링 완료")
    
    # ===== 3단계: 조합 생성 =====
    print("\n[3단계] 부품 조합 생성 중 (3~5개)...")
    
    messages = create_combo_messages(budget, purpose, notes, filtered_parts)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    
    combos_text = response.choices[0].message.content
    combos = extract_combos(combos_text)
    print(f"조합 생성 완료: {len(combos)}개")
    
    # ===== 4단계: 호환성 체크 =====
    print("\n[4단계] 호환성 체크 중...")
    
    compatible_combos = []
    for i, combo in enumerate(combos, 1):
        print(f"\n  조합 {i} 체크 중...")
        print(f"  조합 내용 (처음 200자): {combo[:200]}...")
        
        compat_result = check_compatibility(combo, client)
        
        print(f"  호환성 결과: {compat_result['호환됨']}")
        print(f"  문제점: {compat_result.get('문제점', [])}")
        print(f"  경고사항: {compat_result.get('경고사항', [])}")
        
        if compat_result['호환됨']:
            compatible_combos.append(combo)
            print(f"    ✅ 호환됨")
        else:
            print(f"    ❌ 호환 안됨")
    
    print(f"\n호환성 체크 완료: {len(compatible_combos)}개 조합이 호환됨")
    
    if len(compatible_combos) == 0:
        return "⚠️ 호환되는 조합을 찾을 수 없습니다. 예산을 조정하거나 요구사항을 완화해주세요."
    
    # ===== 5단계: 최종 출력 =====
    print("\n[5단계] 최종 견적서 작성 중...")
    
    messages = create_final_messages(compatible_combos[:3],budget)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    
    final_quote = response.choices[0].message.content
    
    print("\n" + "="*70)
    print("견적 생성 완료!")
    print("="*70)
    
    return final_quote


def handle_followup(previous_quote, user_request, vector_db=None):
    """
    후속 질문 처리
    
    Args:
        previous_quote: 이전 견적
        user_request: 사용자 변경 요청
        vector_db: 벡터DB 객체
    
    Returns:
        수정된 견적 텍스트
    """
    
    print("\n" + "="*70)
    print("견적 수정 시작")
    print("="*70)
    
    # ===== 6-A단계: 변경 요청 분석 =====
    print("\n[6-A단계] 변경 요청 분석 중...")
    
    messages = create_followup_analysis_messages(previous_quote, user_request)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    
    change_analysis = response.choices[0].message.content
    print(f"분석 결과:\n{change_analysis}")
    
    # ===== 6-B단계: 새 부품 검색 =====
    print("\n[6-B단계] 새 부품 검색 중...")
    
    # 변경된 부품 카테고리 추출
    changed_category = extract_changed_category(change_analysis)
    print(f"변경 부품: {changed_category}")
    
    # 새 키워드 생성 (간단 버전)
    # 실제로는 0단계부터 다시 실행해야 함
    if vector_db:
        new_parts = {
            changed_category: vector_db.search(
                category=changed_category.lower(),
                query=user_request,
                top_k=20
            )
        }
    
    
    # LLM 필터링
    new_parts_text = format_parts_list(new_parts)
    
    # ===== 6-C단계: 재조합 =====
    print("\n[6-C단계] 새 견적 생성 중...")
    
    messages = create_followup_recombine_messages(
        previous_quote,
        change_analysis,
        new_parts_text
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages
    )
    
    new_quote = response.choices[0].message.content
    
    # ===== 호환성 재체크 =====
    print("\n[4단계] 호환성 재체크 중...")
    compat_result = check_compatibility(new_quote, client)
    
    if not compat_result['호환됨']:
        print(f"⚠️ 경고: 호환성 문제 발생")
        print(f"문제점: {compat_result.get('문제점', [])}")
    else:
        print(f"✅ 호환성 확인 완료")
    
    print("\n" + "="*70)
    print("견적 수정 완료!")
    print("="*70)
    
    return new_quote


# ===== 헬퍼 함수 =====

def extract_combos(combos_text):
    """
    조합 텍스트에서 개별 조합 추출
    
    Returns:
        조합 문자열 리스트 (compatibility.py가 파싱함)
    """
    combos = []
    
    # "━━━━━━" 로 구분
    parts = combos_text.split("━━━━━━━━━━━━━━━━━━━━")
    
    for part in parts:
        # "조합"이라는 단어와 부품 정보(▪️)가 있으면 유효한 조합
        if ("조합" in part or "순위" in part) and "▪️" in part:
            combos.append(part.strip())
    
    return combos


def extract_changed_category(change_analysis):
    """변경 분석에서 카테고리 추출"""
    match = re.search(r'변경 부품:\s*(.+)', change_analysis)
    if match:
        return match.group(1).strip()
    return "CPU"  # 기본값




   