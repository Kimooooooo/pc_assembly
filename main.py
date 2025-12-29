# main.py
import openai
import streamlit as st
import re
from prompts import *
from compatibility import check_compatibility
from utils import parse_keywords, web_search
from config import OPENAI_API_KEY

if not OPENAI_API_KEY:
    st.error("⚠️ config.py에 API 키가 없습니다.")
    st.stop()

client = openai.OpenAI(api_key=OPENAI_API_KEY)

def generate_quote(budget, purpose, notes, vector_db=None):
    status_text = st.empty()
    
    # ---------------------------------------------------------
    # 1단계: 검색어 생성
    # ---------------------------------------------------------
    status_text.text("🔍 [1/4] 사용자 요구사항 분석 중...")
    prompt_content = SEARCH_KEYWORDS_PROMPT.format(budget=budget, user_request=f"{purpose} / {notes}")
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt_content}]
    )
    keywords_map = parse_keywords(response.choices[0].message.content)
    
    # ---------------------------------------------------------
    # 2단계: 분산 검색
    # ---------------------------------------------------------
    status_text.text("💾 [2/4] 부품 데이터 수집 중...")
    searched_parts_text = ""
    
    if vector_db:
        for category, kw_list in keywords_map.items():
            merged_results = []
            seen = set()
            for kw in kw_list:
                results = vector_db.search(category=category, query=kw, top_k=7)
                for item in results:
                    if item['제품명'] not in seen:
                        seen.add(item['제품명'])
                        merged_results.append(item)
            
            searched_parts_text += f"\n[{category}]\n"
            for item in merged_results[:25]:
                searched_parts_text += f"- {item['제품명']} ({item['가격']}원)\n"

    # ---------------------------------------------------------
    # 3단계: 견적 후보 5개 생성
    # ---------------------------------------------------------
    status_text.text("🤖 [3/4] 최적의 견적 후보 5개 생성 중...")
    
    quote_prompt = GENERATE_QUOTE_PROMPT.format(
        budget=budget,
        user_request=f"{purpose} {notes}",
        filtered_parts=searched_parts_text
    )
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": quote_prompt}],
        temperature=0.7
    )
    raw_quote_text = response.choices[0].message.content
    
    # ---------------------------------------------------------
    # 4단계: 호환성 필터링 및 최종 3개 선별 (핵심 로직)
    # ---------------------------------------------------------
    status_text.text("✅ [4/4] 호환성 검사 및 최종 선별 중...")
    
    # "조합 1", "조합 2" 등을 기준으로 텍스트 분리
    # 정규식: "조합 숫자" 패턴으로 쪼개되, 패턴도 포함시킴
    split_pattern = r'(?=조합\s*\d+)'
    candidates = re.split(split_pattern, raw_quote_text)
    
    valid_quotes = []
    
    # 각 후보 견적을 검사
    for candidate in candidates:
        if len(candidate.strip()) < 30: continue # 빈 줄 패스
        
        # 1. 호환성 체크
        check_res = check_compatibility(candidate, client)
        
        # 2. 통과한 경우에만 리스트에 추가 (담을 때 결과도 같이 담음)
        if check_res['호환됨']:
            valid_quotes.append({
                'text': candidate.strip(),
                'check': check_res
            })
        else:
            print(f"❌ 호환성 탈락: {candidate[:50]}... -> 이유: {check_res['문제점']}")

    # ---------------------------------------------------------
    # 5단계: 최종 출력 (상위 3개만)
    # ---------------------------------------------------------
    final_output_md = ""
    
    if not valid_quotes:
        return "⚠️ 호환되는 견적을 찾지 못했습니다. 예산을 조정하거나 요구사항을 변경해보세요."

    # 최대 3개까지만 출력
    top_picks = valid_quotes[:3]
    
    for i, item in enumerate(top_picks, 1):
        q_text = item['text']
        check_res = item['check']
        
        # 원래 텍스트의 "조합 N (특징)" 부분을 "추천 견적 N (특징)"으로 교체
        # 예: "조합 4 (대안)" -> "추천 견적 2 (대안)" 처럼 순서 재정렬 효과
        header_match = re.match(r'조합\s*\d+(.*)', q_text)
        header_suffix = header_match.group(1) if header_match else ""
        
        # 본문에서 첫 줄(제목) 제거하고 다시 조립
        body_text = q_text.split('\n', 1)[1] if '\n' in q_text else q_text
        
        final_output_md += f"\n\n---"
        final_output_md += f"\n### 🏆 추천 견적 {i}{header_suffix}"
        final_output_md += f"\n{body_text}"
        
        # 경고사항이 있다면 표시 (호환됨=True여도 경고는 있을 수 있음)
        if check_res['경고사항']:
            final_output_md += f"\n\n**:orange[💡 참고사항:]**"
            for msg in check_res['경고사항']:
                final_output_md += f"\n- {msg}"

    status_text.empty()
    return final_output_md

def handle_followup(history, user_input, vector_db):
    return "현재 수정 기능 점검 중입니다."