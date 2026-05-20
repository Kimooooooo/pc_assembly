import openai
import re
from prompts import SYSTEM_PROMPT, SEARCH_KEYWORDS_PROMPT, GENERATE_QUOTE_PROMPT
from compatibility import check_compatibility
from utils import parse_keywords
from config import OPENAI_API_KEY

if not OPENAI_API_KEY:
    raise EnvironmentError("OPENAI_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")

client = openai.OpenAI(api_key=OPENAI_API_KEY)


def generate_quote(budget, purpose, notes, vector_db=None, on_status=None):
    def status(msg):
        if on_status:
            on_status(msg)

    # 1단계: 검색어 생성
    status("[1/4] 사용자 요구사항 분석 중...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": SEARCH_KEYWORDS_PROMPT.format(
                budget=budget, user_request=f"{purpose} / {notes}"
            )}
        ]
    )
    keywords_map = parse_keywords(response.choices[0].message.content)

    # 2단계: 벡터 검색
    status("[2/4] 부품 데이터 수집 중...")
    searched_parts_text = ""
    if vector_db:
        for category, kw_list in keywords_map.items():
            merged_results, seen = [], set()
            for kw in kw_list:
                for item in vector_db.search(category=category, query=kw, top_k=7):
                    if item['제품명'] not in seen:
                        seen.add(item['제품명'])
                        merged_results.append(item)
            searched_parts_text += f"\n[{category}]\n"
            for item in merged_results[:25]:
                searched_parts_text += f"- {item['제품명']} ({item['가격']}원)\n"

    # 3단계: 견적 후보 5개 생성
    status("[3/4] 견적 후보 5개 생성 중...")
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": GENERATE_QUOTE_PROMPT.format(
                budget=budget,
                user_request=f"{purpose} {notes}",
                filtered_parts=searched_parts_text
            )}
        ],
        temperature=0.7
    )
    raw_quote_text = response.choices[0].message.content

    # 4단계: 호환성 필터링
    status("[4/4] 호환성 검사 중...")
    candidates = re.split(r'(?=조합\s*\d+)', raw_quote_text)
    valid_quotes = []
    for candidate in candidates:
        if len(candidate.strip()) < 30:
            continue
        check_res = check_compatibility(candidate, client)
        if check_res['호환됨']:
            valid_quotes.append({'text': candidate.strip(), 'check': check_res})

    if not valid_quotes:
        return "호환되는 견적을 찾지 못했습니다. 예산을 조정하거나 요구사항을 변경해보세요."

    # 최대 3개 출력
    final_md = ""
    for i, item in enumerate(valid_quotes[:3], 1):
        q_text = item['text']
        m = re.match(r'조합\s*\d+(.*)', q_text)
        header_suffix = m.group(1) if m else ""
        body_text = q_text.split('\n', 1)[1] if '\n' in q_text else q_text

        final_md += f"\n\n---\n### 추천 견적 {i}{header_suffix}\n{body_text}"

        if item['check']['경고사항']:
            warnings = "\n".join(f"- {msg}" for msg in item['check']['경고사항'])
            final_md += f"\n\n**참고사항:**\n{warnings}"

    return final_md


def handle_followup(previous_quote, user_request, vector_db=None):
    # TODO: Django 전환 후 구현 예정
    raise NotImplementedError("견적 수정 기능은 구현 중입니다.")
