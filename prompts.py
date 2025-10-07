# prompts.py

"""
PC 견적 추천 시스템 프롬프트 모음
"""

# ========================================
# System Prompt
# ========================================
SYSTEM_PROMPT = """
당신은 컴퓨터 부품 조합 전문가입니다.

**절대 규칙 (위반 시 심각한 문제 발생):**
1. ⚠️ 예산 초과 절대 금지 - 총 가격 ≤ 사용자 예산
2. ⚠️ 사용자 요청 100% 반영 필수
   - "화이트 케이스" → 반드시 화이트
   - "AMD CPU" → Intel 금지
   - "조용한" → 저소음 부품 선택

**역할:**
1. 사용자의 예산, 목적, 참고사항을 분석
2. 주어진 부품 목록에서 최적 조합 생성
3. 호환성과 가성비를 고려한 추천
"""


# ========================================
# 0-A단계: 게임/프로그램 인식 프롬프트
# ========================================
RECOGNITION_PROMPT = """
사용자 참고사항:
{notes}

**작업:**
참고사항에서 게임/프로그램/소프트웨어를 추출하고, 당신이 사양을 아는지 판단하세요.

**판단 기준:**
- 알고 있음: 당신의 학습 데이터에 권장 사양 정보가 있음
- 모름: 최신 게임/프로그램이거나 학습 데이터에 없음

**출력 형식:**

[알고 있는 항목]
- 오버워치 (중급 게임, RTX 4060급, 6코어 CPU)
- 포토샵 (RAM 32GB 필요, 멀티코어 CPU)
- 블렌더 (GPU 렌더링, VRAM 8GB+)

[모르는 항목]
- GTA 6 (2025년 출시 예정, 정보 없음)
- 언리얼 엔진 5.4 (최신 버전, 정보 부족)

[기타 요구사항]
- 화이트 케이스
- 조용한 쿨러
- RGB 라이팅
"""


# ========================================
# 0-B단계: 쿼리 변환 (기본)
# ========================================
QUERY_TRANSLATION_PROMPT = """
사용자 요청:
- 예산: {budget}원
- 목적: {purpose}
- 참고사항: {notes}

**작업:**
PC 부품 검색을 위한 키워드를 생성하세요.

**변환 규칙:**

1. 예산에 맞는 등급 추론
   - 50만원 이하: 보급형, 저가, 가성비
   - 50~100만원: 중급, 가성비
   - 100~150만원: 고급, 고성능
   - 150만원 이상: 최고급, 플래그십

2. 게임/프로그램별 사양 (당신의 지식 활용):

   **게임:**
   - 저사양: 롤, 발로란트, 스타크래프트2
     → GPU: GTX 1650급, CPU: 4코어
   
   - 중사양: 오버워치, 배틀필드, 포르자
     → GPU: RTX 4060급 (8GB), CPU: 6코어
   
   - 고사양: 사이버펑크 2077, 워해머 토탈워, 스타필드
     → GPU: RTX 4070급 (12GB), CPU: 8코어
   
   **작업 프로그램:**
   - 포토샵/일러스트: RAM 32GB, 멀티코어 CPU
   - 영상편집 (프리미어): GPU 중요, RAM 32GB, 8코어
   - 3D 작업 (블렌더): GPU VRAM 12GB, 멀티코어
   - AI/딥러닝: GPU VRAM 최대, RAM 64GB
   - CAD/건축: GPU 중요, CPU 싱글코어 성능

3. 특정 요청사항 반영:
   - "화이트 케이스" → 케이스 키워드에 "화이트" 포함
   - "AMD CPU" → CPU 키워드에 "AMD" 포함
   - "조용한" → 쿨러 키워드에 "저소음" 포함
   - "RGB" → 케이스/쿨러에 "RGB" 포함

4. 저장장치 선택:
   - 기본: SSD만 (빠른 속도)
   - 영상편집/대용량: SSD + HDD
   - 초저예산: HDD만

**출력 형식:**

[CPU 검색 키워드]
중급 게이밍 6코어 효율적

[GPU 검색 키워드]
중급 게이밍 8GB VRAM RTX 4060급

[메인보드 검색 키워드]
게이밍 안정적 DDR5

[RAM 검색 키워드]
DDR5 16GB 게이밍

[파워 검색 키워드]
650W 안정적

[케이스 검색 키워드]
미들타워 화이트 쿨링

[SSD 검색 키워드]
NVMe 500GB 빠른속도

[HDD 검색 키워드]
없음

[쿨러 검색 키워드]
공랭 저소음
"""


# ========================================
# 0-C단계: 쿼리 변환 (검색 결과 포함)
# ========================================
QUERY_TRANSLATION_WITH_SEARCH_PROMPT = """
사용자 요청:
- 예산: {budget}원
- 목적: {purpose}
- 참고사항: {notes}

웹 검색 결과:
{search_results}

**작업:**
당신의 지식 + 웹 검색 결과를 결합하여 부품 검색 키워드를 생성하세요.

**변환 예시:**

검색 결과: "GTA 6 권장 - RTX 4070 Ti, Ryzen 7 7800X3D, 16GB RAM"
→ GPU 키워드: "고성능 게이밍 RTX 4070급 12GB VRAM"
→ CPU 키워드: "고성능 8코어 게이밍 AMD"
→ RAM 키워드: "DDR5 16GB 고속"

검색 결과: "언리얼 엔진 5.4 권장 - RTX 4060 이상, 8코어, 32GB RAM"
→ GPU 키워드: "작업용 RTX 4060급 VRAM"
→ CPU 키워드: "멀티코어 8코어 작업용"
→ RAM 키워드: "DDR5 32GB 대용량"

**저장장치 판단:**
- 기본: SSD만
- 영상편집/대용량: SSD + HDD
- 초저예산: HDD만

**출력 형식:**

[CPU 검색 키워드]
고성능 8코어 게이밍

[GPU 검색 키워드]
고성능 게이밍 RTX 4070급 12GB VRAM

[메인보드 검색 키워드]
게이밍 안정적 DDR5

[RAM 검색 키워드]
DDR5 16GB 고속

[파워 검색 키워드]
750W 안정적

[케이스 검색 키워드]
미들타워 쿨링

[SSD 검색 키워드]
NVMe 1TB 빠른속도

[HDD 검색 키워드]
없음

[쿨러 검색 키워드]
공랭 고성능
"""


# ========================================
# 1단계: 부품 필터링 프롬프트
# ========================================
FILTER_PARTS_PROMPT = """
사용자 요청:
- 예산: {budget}원
- 목적: {purpose}
- 참고사항: {notes}

부품 후보 (각 카테고리 상위 20개):
{parts_list}

**절대 규칙:**
- 예산 초과 부품은 제외
- 참고사항의 요구사항 반영 (화이트, AMD 등)

**작업:**
위 부품 중에서 사용자 요청에 적합한 부품만 선별하세요.
각 카테고리별로 5~10개 정도만 남기세요.

**선별 기준:**
1. 예산에 맞는 가격대
2. 목적에 맞는 성능
3. 참고사항 반영

**출력 형식:**

[CPU 선별 결과]
1. AMD 라이젠7 7800X3D (453,000원) - 8코어 게이밍 특화
2. Intel 코어 14700K (489,000원) - 멀티태스킹 우수
3. AMD 라이젠5 5600 (189,000원) - 가성비 좋음
...

[GPU 선별 결과]
1. RTX 4070 (689,000원) - 고사양 게이밍
2. RTX 4060 (389,000원) - 가성비 중급
...

[메인보드 선별 결과]
...

[RAM 선별 결과]
...

[파워 선별 결과]
...

[케이스 선별 결과]
...

[SSD 선별 결과]
...

[HDD 선별 결과]
(필요시만)

[쿨러 선별 결과]
...
"""


# ========================================
# 2단계: 조합 생성 프롬프트
# ========================================
GENERATE_COMBOS_PROMPT = """
사용자 요청:
- 예산: {budget}원
- 목적: {purpose}
- 참고사항: {notes}

필터링된 부품 목록:
{filtered_parts}

**절대 규칙:**
1. 총 가격은 반드시 {budget}원 이하 (초과 절대 금지!)
2. 참고사항의 모든 요구사항 100% 반영
   - 특정 색상 요청 시 반드시 해당 색상
   - 특정 게임/프로그램 언급 시 반드시 구동 가능한 사양
   - 특정 제조사 요청 시 해당 제조사만 선택

**작업:**
위 부품으로 3~5개의 서로 다른 조합을 만드세요.

**조합 기준:**
1. 예산 범위 내 (초과 절대 금지!)
2. 목적에 맞는 성능
3. 참고사항 100% 반영
4. 각 조합은 차별화
   - 예: 가성비형, 균형형, 고성능형

**저장장치:**
- SSD는 기본 포함
- HDD는 필요시만 추가 (예산/용도에 따라)

**출력 형식:**

━━━━━━━━━━━━━━━━━━━━
조합 1: 가성비 게이밍 조합
━━━━━━━━━━━━━━━━━━━━
▪️ CPU: AMD 라이젠5 5600 (189,000원)
▪️ 메인보드: ASRock B550M (129,000원)
▪️ RAM: 삼성 DDR4 16GB (45,000원)
▪️ GPU: RTX 4060 (389,000원)
▪️ 파워: 마이크로닉스 650W (79,000원)
▪️ 케이스: ABKO 화이트 (69,000원)
▪️ SSD: 삼성 500GB (59,000원)
▪️ 쿨러: 기본 쿨러 포함

💰 총가격: 959,000원
📝 특징: 예산 내 최대 가성비, 1080p 게이밍 최적

━━━━━━━━━━━━━━━━━━━━
조합 2: 균형형 조합
━━━━━━━━━━━━━━━━━━━━
...

(3~5개 조합 작성)
"""


# ========================================
# 3단계: LLM 호환성 보조 판단
# ========================================
LLM_COMPATIBILITY_CHECK_PROMPT = """
다음 PC 부품 조합의 호환성을 판단해주세요.

부품 조합:
{combo}

규칙 기반 체크 결과:
{rule_check_result}

애매한 부분:
{uncertain_items}

**작업:**
위 정보를 바탕으로 최종 호환성을 판단하세요.

**출력 형식:**

호환 여부: ✅ 호환됨 / ❌ 호환 안됨

문제점:
- (문제가 있으면 나열, 없으면 "없음")

경고사항:
- (주의사항이 있으면 나열, 없으면 "없음")
"""


# ========================================
# 4단계: 최종 출력 프롬프트
# ========================================
FINAL_OUTPUT_PROMPT = """
호환성 검사 완료된 조합 (호환되는 것만):

{compatible_combos}

**작업:**
호환되는 조합 중 최대 3개만 선택하여 사용자에게 보여주세요.

**선택 기준:**
1. 호환성이 완벽한 것 우선
2. 예산에 가까운 것 우선
3. 사용자 요구사항을 가장 잘 반영한 것

**출력 형식:**

━━━━━━━━━━━━━━━━━━━━
💻 추천 PC 견적 (1순위)
━━━━━━━━━━━━━━━━━━━━

💰 총 예산: 980,000원

📦 부품 구성:
▪️ CPU: AMD 라이젠5 5600 (189,000원)
▪️ 메인보드: ASRock B550M (129,000원)
▪️ RAM: 삼성 DDR4 16GB (45,000원)
▪️ GPU: RTX 4060 (389,000원)
▪️ 파워: 마이크로닉스 650W (79,000원)
▪️ 케이스: ABKO 화이트 (69,000원)
▪️ SSD: 삼성 500GB (59,000원)
▪️ 쿨러: 기본 쿨러 포함

✅ 호환성: 완벽 호환

📝 선택 이유:
예산 내에서 오버워치 최고옵션 구동 가능하며, 화이트 케이스 요청을 반영했습니다.

━━━━━━━━━━━━━━━━━━━━
💡 다른 추천 조합
━━━━━━━━━━━━━━━━━━━━

2순위: 균형형 (950,000원)
- 비슷한 성능, 3만원 절약

3순위: 고성능형 (1,000,000원)
- RTX 4060 Ti 사용, 예산과 동일
"""


# ========================================
# 5단계: 후속 질문 - 변경 분석
# ========================================
FOLLOWUP_ANALYSIS_PROMPT = """
사용자가 선택한 견적:
{selected_quote}

사용자 요청:
"{user_request}"

**작업:**
사용자가 어떤 변경을 원하는지 분석하세요.

**출력 형식:**

변경 부품: CPU
기존 부품: Intel 코어 14700K
변경 방향: AMD로 교체
예산 유지: 예
성능 유지: 예
추가 요구사항: 없음
"""


# ========================================
# 6단계: 후속 질문 - 재조합
# ========================================
FOLLOWUP_RECOMBINE_PROMPT = """
기존 견적:
{previous_quote}

변경 요청 분석:
{change_analysis}

새로운 부품 후보:
{new_parts}

**절대 규칙:**
- 예산 초과 금지
- 사용자 변경 요청 100% 반영

**작업:**
변경 요청을 반영한 새 견적을 작성하세요.

**주의사항:**
1. 요청된 부품만 변경하되, 호환성 문제 발생 시 관련 부품도 함께 조정
   - 예: CPU Intel → AMD 변경 시, 메인보드도 소켓 맞춰서 변경
   - 예: GPU 업그레이드 시, 파워 용량 부족하면 파워도 교체
2. 예산은 기존과 비슷하게 유지 (±10% 허용)
3. 성능은 유지 또는 향상
4. 변경된 부품에는 🔄 표시

**출력 형식:**

━━━━━━━━━━━━━━━━━━━━
💻 수정된 PC 견적
━━━━━━━━━━━━━━━━━━━━

💰 총 예산: 1,020,000원 (↑ 40,000원)

📦 부품 구성:

🔄 CPU: AMD 라이젠7 7800X3D (453,000원)
   (변경: Intel 14700K → AMD 7800X3D)

🔄 메인보드: ASUS B650 (189,000원)
   (변경 이유: CPU 소켓 변경으로 함께 교체)

▪️ RAM: 삼성 DDR5 32GB (159,000원)
▪️ GPU: RTX 4070 (689,000원)
▪️ 파워: 마이크로닉스 750W (89,000원)
▪️ 케이스: ABKO 화이트 (69,000원)
▪️ SSD: 삼성 1TB (99,000원)
▪️ 쿨러: 기본 쿨러 포함

✅ 호환성: 완벽 호환

📝 변경 사유:
CPU를 AMD로 변경하면서 소켓이 달라져 메인보드도 B650으로 교체했습니다.
총 4만원 증가했으나 게이밍 성능은 동등 수준입니다.
"""


# ========================================
# 헬퍼 함수
# ========================================

def create_recognition_messages(notes):
    """0-A단계: 게임/프로그램 인식용 메시지"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": RECOGNITION_PROMPT.format(
            notes=notes if notes else "없음"
        )}
    ]


def create_query_translation_messages(budget, purpose, notes):
    """0-B단계: 쿼리 변환용 메시지 (기본)"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": QUERY_TRANSLATION_PROMPT.format(
            budget=f"{budget:,}",
            purpose=purpose,
            notes=notes if notes else "없음"
        )}
    ]


def create_query_translation_with_search_messages(budget, purpose, notes, search_results):
    """0-C단계: 쿼리 변환용 메시지 (검색 결과 포함)"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": QUERY_TRANSLATION_WITH_SEARCH_PROMPT.format(
            budget=f"{budget:,}",
            purpose=purpose,
            notes=notes if notes else "없음",
            search_results=search_results
        )}
    ]


def create_filter_messages(budget, purpose, notes, parts):
    """1단계: 부품 필터링용 메시지"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FILTER_PARTS_PROMPT.format(
            budget=f"{budget:,}",
            purpose=purpose,
            notes=notes if notes else "없음",
            parts_list=format_parts_list(parts)
        )}
    ]


def create_combo_messages(budget, purpose, notes, filtered_parts):
    """2단계: 조합 생성용 메시지"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": GENERATE_COMBOS_PROMPT.format(
            budget=f"{budget:,}",
            purpose=purpose,
            notes=notes if notes else "없음",
            filtered_parts=filtered_parts
        )}
    ]


def create_llm_compat_messages(combo, rule_result, uncertain):
    """3단계: LLM 호환성 보조 판단"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": LLM_COMPATIBILITY_CHECK_PROMPT.format(
            combo=combo,
            rule_check_result=rule_result,
            uncertain_items=uncertain if uncertain else "없음"
        )}
    ]


def create_final_messages(compatible_combos):
    """4단계: 최종 출력용 메시지"""
    combos_text = "\n\n".join(compatible_combos) if compatible_combos else "호환되는 조합이 없습니다."
    
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FINAL_OUTPUT_PROMPT.format(
            compatible_combos=combos_text
        )}
    ]


def create_followup_analysis_messages(selected_quote, user_request):
    """5단계: 후속 질문 분석"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FOLLOWUP_ANALYSIS_PROMPT.format(
            selected_quote=selected_quote,
            user_request=user_request
        )}
    ]


def create_followup_recombine_messages(previous_quote, change_analysis, new_parts):
    """6단계: 후속 질문 재조합"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": FOLLOWUP_RECOMBINE_PROMPT.format(
            previous_quote=previous_quote,
            change_analysis=change_analysis,
            new_parts=new_parts
        )}
    ]


def format_parts_list(parts):
    """
    부품 리스트를 텍스트로 포맷팅
    
    Args:
        parts: {
            "CPU": [{"제품명": "...", "가격": 000000}, ...],
            "GPU": [...],
            ...
        }
    
    Returns:
        포맷팅된 문자열
    """
    result = ""
    for category, items in parts.items():
        result += f"\n[{category}]\n"
        for i, item in enumerate(items[:20], 1):  # 상위 20개
            result += f"{i}. {item['제품명']} ({item['가격']:,}원)\n"
    return result