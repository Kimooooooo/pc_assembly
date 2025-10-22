# compatibility.py

# compatibility.py (최종 버전)

import re
import ast
from power_calculator import calculate_total_power, check_power_compatibility


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_compatibility(combo, openai_client=None):
    """
    부품 조합 호환성 종합 체크 (LLM 보조 포함)
    """
    rule_result, uncertain = rule_based_check(combo)
    
    # 2. LLM 보조 판단 (파워는 항상 LLM이 재확인)
    if openai_client:
        llm_result = llm_assisted_check(combo, rule_result, uncertain, openai_client)
        
        # LLM 결과 통합
        if not llm_result['호환됨']:
            rule_result['호환됨'] = False
            rule_result['문제점'].extend(llm_result['문제점'])
        
        rule_result['경고사항'].extend(llm_result['경고사항'])
    
    # 3. 결과 텍스트 설정
    rule_result['결과_텍스트'] = "호환됨" if rule_result['호환됨'] else "호환 안됨"
    
    return rule_result


def rule_based_check(combo):
    """
    규칙 기반 호환성 체크
    """
    issues = []
    warnings = []
    uncertain = []
    
    parts = extract_parts_from_combo(combo)
    
    if not parts or len(parts) < 3:
        return {
            "호환됨": False,
            "문제점": ["부품 정보가 불완전하거나 파싱할 수 없습니다."],
            "경고사항": [],
            "상세": {}
        }, []
    
    cpu_info = parts.get('CPU')
    mb_info = parts.get('MAINBORD')
    ram_info = parts.get('RAM')
    case_info = parts.get('CASE')
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 1. CPU ↔ 메인보드 소켓/타입 체크
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    socket_issue = None
    if cpu_info and mb_info:
        socket_issue = check_socket_compatibility(cpu_info, mb_info)
        if socket_issue:
            issues.append(f"❌ 소켓/칩셋 불일치: {socket_issue}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. RAM ↔ 메인보드 DDR 타입 체크
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ddr_issue = None
    if cpu_info and mb_info and ram_info:
        ddr_issue = check_ddr_compatibility(cpu_info, mb_info, ram_info)
        if ddr_issue:
            issues.append(f"❌ 메모리 타입 불일치: {ddr_issue}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. 전력 체크 (1차 검증 + LLM 재확인 필수)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    power_result = None
    if '파워' in parts:
        power_result = check_power_compatibility(parts)
        
        # 1차 검증: 명백한 부족은 즉시 불합격
        if not power_result['충분함']:
            issues.append(
                f"❌ 파워 부족: 총 소비 {power_result['총소비']}W, "
                f"파워 용량 {power_result['파워용량']}W "
                f"(안전 용량 {power_result['안전용량']}W 기준)"
            )
        elif power_result['여유율'] < 10:
            warnings.append(
                f"⚠️ 파워 여유 매우 적음: {power_result['여유율']}% 남음 - 업그레이드 권장"
            )
        elif power_result['여유율'] < 20:
            warnings.append(
                f"⚠️ 파워 여유 적음: {power_result['여유율']}% 남음"
            )
        
        # ★ 핵심: 파워는 항상 LLM이 재확인하도록 uncertain에 추가
        power_detail = (
            f"파워 검증 필수 재확인:\n"
            f"- CPU: {parts.get('CPU', {}).get('제품명', '알 수 없음')}\n"
            f"- GPU: {parts.get('GPU', {}).get('제품명', '알 수 없음')}\n"
            f"- 파워: {parts.get('파워', {}).get('제품명', '알 수 없음')}\n"
            f"- 1차 계산 결과: 총 소비 {power_result['총소비']}W, "
            f"파워 용량 {power_result['파워용량']}W, 여유율 {power_result['여유율']}%\n"
            f"- 이 조합이 실제로 안정적인지 재확인 필요"
        )
        uncertain.append(power_detail)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. 폼팩터 체크
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if mb_info and case_info:
        formfactor_status = check_formfactor_compatibility(mb_info, case_info)
        if formfactor_status == "INCOMPATIBLE":
            issues.append("❌ 메인보드와 케이스 폼팩터 불일치. 조립 불가능.")
        elif formfactor_status == "UNCERTAIN":
            uncertain.append("케이스 호환성: 대형 그래픽카드 물리적 간섭 확인 필요")
    
    # 결과 반환
    compatible = len(issues) == 0
    
    return {
        "호환됨": compatible,
        "문제점": issues,
        "경고사항": warnings,
        "상세": {
            "전력": power_result
        }
    }, uncertain


def llm_assisted_check(combo, rule_result, uncertain_items, openai_client):
    """
    LLM을 활용한 보조 판단 (파워 필수 재확인)
    """
    
    uncertain_text = "\n".join(uncertain_items) if uncertain_items else "없음"
    
    rule_info = f"""
1차 규칙 기반 검증 결과:
- 호환 여부: {'✅ 통과' if rule_result['호환됨'] else '❌ 실패'}
- 문제점: {', '.join(rule_result['문제점']) if rule_result['문제점'] else '없음'}
- 경고사항: {', '.join(rule_result['경고사항']) if rule_result['경고사항'] else '없음'}
"""
    
    prompt = f"""
다음 PC 부품 조합의 호환성을 최종 판단해주세요.

조합:
{combo}

{rule_info}

추가 확인 필요 항목:
{uncertain_text}

**🔥 필수 검증 항목 (우선순위순):**

━━━━━━━━━━━━━━━━━━━━
1. ⚡ 파워 용량 재확인 (최우선)
━━━━━━━━━━━━━━━━━━━━
**당신의 지식을 활용하여 반드시 재계산하세요:**

- CPU 실제 소비 전력 확인 (TDP/PPT 기준)
  예: 라이젠 7800X3D = 162W, 인텔 14700K = 253W
  
- GPU 실제 소비 전력 확인 (TGP 기준)
  예: RTX 4090 = 450W, RTX 4070 = 200W, RTX 4060 = 115W
  
- 기타 부품 전력: 약 85W
  (메인보드 50W + RAM 10W + SSD 5W + 쿨러/케이스팬 20W)
  
- **총 소비 전력 = CPU + GPU + 85W**

- **안전 용량 = 파워 용량 * 0.8**
  (예: 650W 파워 → 안전 용량 520W)
  
- **여유율 = (안전 용량 - 총 소비) / 안전 용량 * 100**

**판단 기준:**
- 총 소비 > 안전 용량 → ❌ 불합격
- 여유율 < 10% → ❌ 불합격 (업그레이드 필수)
- 여유율 < 15% → ⚠️ 경고 (여유 부족)
- 여유율 ≥ 15% → ✅ 합격

━━━━━━━━━━━━━━━━━━━━
2. 🔌 CPU ↔ 메인보드 소켓 확인
━━━━━━━━━━━━━━━━━━━━
- AMD Zen4/5 (7000/9000번대) → AM5 소켓 (B650/X670/B850/X870)
- AMD Zen3 (5000번대) → AM4 소켓 (B550/X570)
- Intel 12~14세대 → LGA1700 (Z690/B660/Z790/B760)
- Intel 제조사와 AMD 제조사 절대 혼용 금지

━━━━━━━━━━━━━━━━━━━━
3. 💾 RAM 규격 확인
━━━━━━━━━━━━━━━━━━━━
- DDR5 CPU는 DDR5 RAM만 사용
- DDR4 CPU는 DDR4 RAM만 사용
- 메인보드도 같은 규격 지원해야 함

━━━━━━━━━━━━━━━━━━━━
4. 📦 물리적 간섭 확인
━━━━━━━━━━━━━━━━━━━━
- 대형 GPU (RTX 4070 이상) + 소형 케이스 (ITX) → 주의
- 대형 타워쿨러 + RAM 간섭 가능성
- M-ATX 보드 + ATX 케이스 → 문제 없음

**출력 형식:**

호환 여부: ✅ 호환됨 / ❌ 호환 안됨

━━━━━━━━━━━━━━━━━━━━
검증 단계:
━━━━━━━━━━━━━━━━━━━━

1. ⚡ 파워 검증 (최우선):
   - CPU 소비: [실제 전력]W
   - GPU 소비: [실제 전력]W
   - 기타 부품: 85W
   - 총 소비: [합계]W
   - 파워 용량: [용량]W
   - 안전 용량: [용량×0.8]W
   - 여유율: [계산 결과]%
   - 판정: ✅/❌/⚠️

2. 🔌 소켓 확인:
   - CPU: [제조사/세대]
   - 메인보드: [칩셋]
   - 판정: ✅/❌

3. 💾 RAM 규격:
   - CPU 지원: DDR4/DDR5
   - RAM: DDR4/DDR5
   - 판정: ✅/❌

4. 📦 물리적 확인:
   - 케이스/GPU/보드 크기
   - 판정: ✅/⚠️

━━━━━━━━━━━━━━━━━━━━
문제점:
━━━━━━━━━━━━━━━━━━━━
- (문제가 있으면 나열, 없으면 "없음")

━━━━━━━━━━━━━━━━━━━━
경고사항:
━━━━━━━━━━━━━━━━━━━━
- (주의사항이 있으면 나열, 없으면 "없음")
"""
    
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 PC 부품 호환성 전문가입니다. 특히 파워 용량 계산에 정확해야 합니다."},
                {"role": "user", "content": prompt}
            ]
        )
        
        llm_response = response.choices[0].message.content
        return parse_llm_response(llm_response)
        
    except Exception as e:
        print(f"LLM 호출 실패: {e}")
        return {
            "호환됨": True,
            "문제점": [],
            "경고사항": ["LLM 판단 실패 - 수동 확인 필수"]
        }


def parse_llm_response(llm_response):
    """LLM 응답 파싱"""
    compatible = "✅" in llm_response.split('\n')[0]
    
    issues = extract_issues(llm_response)
    warnings = extract_warnings(llm_response)
    
    return {
        "호환됨": compatible,
        "문제점": issues,
        "경고사항": warnings
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬퍼 함수들
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_parts_from_combo(combo):
    """
    조합 텍스트 또는 딕셔너리에서 부품 정보 추출
    """
    parts = {}
    if isinstance(combo, dict):
        parts = combo
    else:
        lines = str(combo).split('\n')
        for line in lines:
            if '▪️' in line or '-' in line:
                for category in ['CPU', 'GPU', 'MAINBORD', 'RAM', 'POWER', 'CASE', 'SSD', 'HDD', 'COOLER']:
                    if category in line:
                        match = re.search(rf'{category}:\s*(.+?)\s*\(', line)
                        if match:
                            parts[category] = {"제품명": match.group(1).strip(), "상세정보": {}}
    
    # 상세정보 문자열을 딕셔너리로 변환
    for category, part_info in parts.items():
        if '상세정보' in part_info and isinstance(part_info['상세정보'], str):
            try:
                part_info['상세정보'] = ast.literal_eval(part_info['상세정보'])
            except:
                part_info['상세정보'] = {}
        elif '상세정보' not in part_info:
            part_info['상세정보'] = {}

    return parts


def get_part_detail(part_info, key):
    """안전하게 상세정보 딕셔너리에서 값 추출"""
    details = part_info.get('상세정보', {})
    return details.get(key, "").upper().strip()


def get_formfactor_from_name(name):
    """제품명에서 폼팩터 추론"""
    name = name.upper()
    if any(x in name for x in ["M-ATX", "MATX", "M ATX", "MICRO"]):
        return "M-ATX"
    elif "ITX" in name or "MINI" in name:
        return "Mini-ITX"
    else:
        return "ATX"


def check_socket_compatibility(cpu_info, mb_info):
    """CPU ↔ 메인보드 소켓/칩셋 호환성 체크"""
    cpu_manuf = get_part_detail(cpu_info, '제조사') or ("INTEL" if "INTEL" in cpu_info['제품명'].upper() else "AMD")
    mb_manuf_type = get_part_detail(mb_info, '제품 분류')
    
    if "AMD" in cpu_manuf and "AMD" not in mb_manuf_type:
        return f"CPU(AMD)와 메인보드({mb_manuf_type}) 제조사 불일치"
    if "INTEL" in cpu_manuf and "INTEL" not in mb_manuf_type:
        return f"CPU(INTEL)와 메인보드({mb_manuf_type}) 제조사 불일치"
    
    mb_chipset = get_part_detail(mb_info, '세부 칩셋')
    cpu_generation = get_part_detail(cpu_info, '세대 구분') or cpu_info['제품명'].upper()
    
    if "AMD" in cpu_manuf and ("ZEN4" in cpu_generation or "ZEN5" in cpu_generation or "7" in cpu_generation or "8" in cpu_generation or "9" in cpu_generation):
        if not any(c in mb_chipset for c in ["B650", "X670", "B850", "X870", "A620"]):
            return f"AMD 젠4/5세대 CPU와 MB 칩셋({mb_chipset}) 소켓 불일치 예상"
            
    if "INTEL" in cpu_manuf:
        if "12세대" in cpu_generation or "13세대" in cpu_generation or "14세대" in cpu_generation:
            if not any(c in mb_chipset for c in ["Z690", "B660", "H610", "Z790", "B760", "H770"]):
                 return f"INTEL 12~14세대 CPU와 MB 칩셋({mb_chipset}) 소켓 불일치 예상"
    
    return None


def check_ddr_compatibility(cpu_info, mb_info, ram_info):
    """DDR 타입 호환성 체크"""
    cpu_ddr = get_part_detail(cpu_info, '메모리 규격')
    
    ram_ddr = ""
    ram_name = ram_info['제품명'].upper()
    if "DDR5" in ram_name: ram_ddr = "DDR5"
    elif "DDR4" in ram_name: ram_ddr = "DDR4"
    else: return "RAM DDR 타입 불명확"

    if cpu_ddr != ram_ddr:
        return f"CPU({cpu_ddr})와 RAM({ram_ddr}) 메모리 타입 불일치"
        
    return None


def check_formfactor_compatibility(mb_info, case_info):
    """메인보드 ↔ 케이스 폼팩터 체크"""
    mb_formfactor = get_part_detail(mb_info, '폼팩터')
    if not mb_formfactor:
        mb_formfactor = get_formfactor_from_name(mb_info['제품명'])

    case_support = get_part_detail(case_info, '메인보드 지원')
    if not case_support:
        case_name = case_info['제품명'].upper()
        if "ITX" in case_name: case_support = "MINI-ITX"
        elif any(x in case_name for x in ["M-ATX", "MATX", "MICRO"]): case_support = "M-ATX, MINI-ITX"
        else: case_support = "ATX, M-ATX, MINI-ITX"
        
    if mb_formfactor not in case_support:
        return "INCOMPATIBLE"

    return "UNCERTAIN"


def extract_issues(llm_response):
    """LLM 응답에서 문제점 추출"""
    issues = []
    pattern = r'문제점:\s*\n(.+?)(?=\n\n|경고사항:|$)'
    match = re.search(pattern, llm_response, re.DOTALL)
    if match:
        content = match.group(1)
        issues = re.findall(r'-\s*(.+)', content)
        issues = [i.strip() for i in issues if i.strip() and i.strip() != "없음"]
    return issues


def extract_warnings(llm_response):
    """LLM 응답에서 경고사항 추출"""
    warnings = []
    pattern = r'경고사항:\s*\n(.+?)(?=\n\n|$)'
    match = re.search(pattern, llm_response, re.DOTALL)
    if match:
        content = match.group(1)
        warnings = re.findall(r'-\s*(.+)', content)
        warnings = [w.strip() for w in warnings if w.strip() and w.strip() != "없음"]
    return warnings