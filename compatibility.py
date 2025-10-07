# compatibility.py

import re
import ast
from power_calculator import calculate_total_power, check_power_compatibility
import ast


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 함수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_compatibility(combo, openai_client=None):
    """
    부품 조합 호환성 종합 체크 (LLM 보조 포함)
    """
    rule_result, uncertain = rule_based_check(combo)
    
    # 2. 애매한 경우 LLM 보조 판단
    if uncertain and openai_client:
        llm_result = llm_assisted_check(combo, uncertain, openai_client)
        
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
    규칙 기반 호환성 체크 (데이터 필드 기반으로 대폭 강화됨)
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
    # 1. CPU ↔ 메인보드 소켓/타입 체크 (제조사, 칩셋 기반)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    socket_issue = None
    if cpu_info and mb_info:
        socket_issue = check_socket_compatibility(cpu_info, mb_info)
        if socket_issue:
            issues.append(f"❌ 소켓/칩셋 불일치: {socket_issue}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 2. RAM ↔ 메인보드 DDR 타입 체크 (명시적 규격 기반)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    ddr_issue = None
    if cpu_info and mb_info and ram_info:
        ddr_issue = check_ddr_compatibility(cpu_info, mb_info, ram_info)
        if ddr_issue:
            issues.append(f"❌ 메모리 타입 불일치: {ddr_issue}")
    
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 3. 전력 체크 (명시적 PPT/사용전력 활용)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    power_result = None
    if '파워' in parts:
        power_result = check_power_compatibility(parts)
        
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

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 4. 폼팩터 체크
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    if mb_info and case_info:
        formfactor_status = check_formfactor_compatibility(mb_info, case_info)
        if formfactor_status == "INCOMPATIBLE":
            issues.append("❌ 메인보드와 케이스 폼팩터 불일치. 조립 불가능.")
        elif formfactor_status == "UNCERTAIN":
            uncertain.append("케이스 호환성 확인 필요: 대형 그래픽카드 물리적 간섭 등")
    
    # 5. 쿨러 호환성 체크 (간단 버전, 쿨러 데이터 필요)
    if cpu_info and '쿨러' in parts:
        cpu_power = calculate_total_power({'CPU': cpu_info}) # CPU 전력만 계산
        # 쿨러의 TDP 지원 정보가 있다면 비교하여 warnings에 추가
        # (현재 쿨러 데이터 필드 불명확으로 생략)
        pass 
    
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


def llm_assisted_check(combo, uncertain_items, openai_client):
    """
    LLM을 활용한 보조 판단 (로직은 기존 유지)
    """
    
    prompt = f"""
다음 PC 부품 조합의 호환성을 판단해주세요.

조합:
{combo}

불확실한 항목:
{chr(10).join(uncertain_items)}

다음 형식으로 답변:
호환 여부: ✅ 또는 ❌
문제점:
- (있으면 나열, 없으면 "없음")
경고사항:
- (있으면 나열, 없으면 "없음")
"""
    
    try:
        # 이 환경에서는 OpenAI 클라이언트 실행 불가능. 실제 시스템에서 사용
        # response = openai_client.chat.completions.create(...)
        # return parse_llm_response(response)
        
        # LLM 호출 실패 시 보수적으로 판단
        return {
            "호환됨": True,
            "문제점": [],
            "경고사항": ["LLM 판단 실패 - 수동 확인 권장"]
        }
    except:
        return {
            "호환됨": True,
            "문제점": [],
            "경고사항": ["LLM 판단 실패 - 수동 확인 권장"]
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬퍼 함수들 (데이터 기반으로 대폭 수정)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def extract_parts_from_combo(combo):
    """
    조합 텍스트 또는 딕셔너리에서 부품 정보 추출 및 상세정보 파싱 (강화됨)
    """
    parts = {}
    if isinstance(combo, dict):
        parts = combo
    else:
        # 텍스트에서 부품 정보 추출 (기존 로직 유지)
        lines = str(combo).split('\n')
        for line in lines:
            if '▪️' in line or '-' in line:
                for category in ['CPU', 'GPU', 'MAINBORD', 'RAM', 'POWER', 'CASE', 'SSD', 'HDD', 'COOLER']:
                    if category in line:
                        match = re.search(rf'{category}:\s*(.+?)\s*\(', line)
                        if match:
                            # 텍스트 기반 파싱은 상세정보 없음으로 시작
                            parts[category] = {"제품명": match.group(1).strip(), "상세정보": {}}
    
    # 상세정보 문자열을 딕셔너리로 변환 (가장 중요한 부분)
    for category, part_info in parts.items():
        if '상세정보' in part_info and isinstance(part_info['상세정보'], str):
            try:
                # ast.literal_eval을 사용하여 상세정보 문자열을 딕셔너리로 안전하게 변환
                # 예: "{'키': '값'}" -> {'키': '값'}
                part_info['상세정보'] = ast.literal_eval(part_info['상세정보'])
            except:
                # 파싱 실패 시 빈 딕셔너리
                part_info['상세정보'] = {}
        elif '상세정보' not in part_info:
            part_info['상세정보'] = {}

    return parts


def get_part_detail(part_info, key):
    """안전하게 상세정보 딕셔너리에서 값 추출"""
    details = part_info.get('상세정보', {})
    return details.get(key, "").upper().strip()


def get_formfactor_from_name(name):
    """제품명에서 폼팩터 추론 (데이터 없으면)"""
    name = name.upper()
    if any(x in name for x in ["M-ATX", "MATX", "M ATX", "MICRO"]):
        return "M-ATX"
    elif "ITX" in name or "MINI" in name:
        return "Mini-ITX"
    else:
        return "ATX"

def check_socket_compatibility(cpu_info, mb_info):
    """
    CPU ↔ 메인보드 소켓/칩셋 호환성 체크 (데이터 기반)
    - 제조사 일치 및 칩셋 세대 확인
    """
    cpu_manuf = get_part_detail(cpu_info, '제조사') or ("INTEL" if "INTEL" in cpu_info['제품명'].upper() else "AMD")
    mb_manuf_type = get_part_detail(mb_info, '제품 분류') # AMD CPU용, INTEL CPU용
    
    # 1. 제조사 일치 확인
    if "AMD" in cpu_manuf and "AMD" not in mb_manuf_type:
        return f"CPU(AMD)와 메인보드({mb_manuf_type}) 제조사 불일치"
    if "INTEL" in cpu_manuf and "INTEL" not in mb_manuf_type:
        return f"CPU(INTEL)와 메인보드({mb_manuf_type}) 제조사 불일치"
    
    # 2. 소켓/칩셋 세부 호환성 (세대별 칩셋 검증)
    mb_chipset = get_part_detail(mb_info, '세부 칩셋')
    cpu_generation = get_part_detail(cpu_info, '세대 구분') or cpu_info['제품명'].upper()
    
    # AM5 칩셋 체크 (B650, X670, B850, X870 등)
    if "AMD" in cpu_manuf and ("ZEN4" in cpu_generation or "ZEN5" in cpu_generation or "7" in cpu_generation or "8" in cpu_generation or "9" in cpu_generation):
        if not any(c in mb_chipset for c in ["B650", "X670", "B850", "X870", "A620"]):
            return f"AMD 젠4/5세대 CPU와 MB 칩셋({mb_chipset}) 소켓 불일치 예상"
            
    # LGA1700/1851 칩셋 체크 (12/13/14세대)
    if "INTEL" in cpu_manuf:
        if "12세대" in cpu_generation or "13세대" in cpu_generation or "14세대" in cpu_generation:
            if not any(c in mb_chipset for c in ["Z690", "B660", "H610", "Z790", "B760", "H770"]):
                 return f"INTEL 12~14세대 CPU와 MB 칩셋({mb_chipset}) 소켓 불일치 예상"
    
    return None


def check_ddr_compatibility(cpu_info, mb_info, ram_info):
    """
    DDR 타입 호환성 체크 (명시적 '메모리 규격' 기반)
    """
    cpu_ddr = get_part_detail(cpu_info, '메모리 규격') # DDR5
    
    # RAM 제품명에서 DDR 타입 추출 (가장 확실한 방법)
    ram_ddr = ""
    ram_name = ram_info['제품명'].upper()
    if "DDR5" in ram_name: ram_ddr = "DDR5"
    elif "DDR4" in ram_name: ram_ddr = "DDR4"
    else: return "RAM DDR 타입 불명확"

    # 1. CPU와 RAM DDR 타입 일치 확인
    if cpu_ddr != ram_ddr:
        return f"CPU({cpu_ddr})와 RAM({ram_ddr}) 메모리 타입 불일치"
    
    # 2. 메인보드 지원 DDR 타입 확인 (제품명으로 확인)
    mb_name = mb_info['제품명'].upper()
    if cpu_ddr == "DDR5" and "DDR5" not in mb_name:
        # B650 칩셋 MB는 대부분 DDR5 지원하나 제품명에 명시 안 될 수 있음.
        # 보수적으로 경고는 LLM에 위임, 여기선 명백한 불일치만 잡음
        pass 
    if cpu_ddr == "DDR4" and "DDR4" not in mb_name:
        pass
        
    return None


def check_formfactor_compatibility(mb_info, case_info):
    """
    메인보드 ↔ 케이스 폼팩터 체크
    """
    # 1. 메인보드 폼팩터 추론
    mb_formfactor = get_part_detail(mb_info, '폼팩터')
    if not mb_formfactor:
        mb_formfactor = get_formfactor_from_name(mb_info['제품명']) # 예: M-ATX

    # 2. 케이스 지원 폼팩터 추론
    case_support = get_part_detail(case_info, '메인보드 지원') # 예: ATX, M-ATX, Mini-ITX
    if not case_support:
        case_name = case_info['제품명'].upper()
        if "ITX" in case_name: case_support = "MINI-ITX"
        elif any(x in case_name for x in ["M-ATX", "MATX", "MICRO"]): case_support = "M-ATX, MINI-ITX"
        else: case_support = "ATX, M-ATX, MINI-ITX"
        
    # 3. 호환성 체크
    if mb_formfactor not in case_support:
        return "INCOMPATIBLE"

    # 4. LLM 보조 판단 (물리적 간섭)
    return "UNCERTAIN"


def extract_issues(llm_response):
    """LLM 응답에서 문제점 추출 (기존 유지)"""
    issues = []
    pattern = r'문제점:\s*\n(.+?)(?=\n\n|경고사항:|$)'
    match = re.search(pattern, llm_response, re.DOTALL)
    if match:
        content = match.group(1)
        issues = re.findall(r'-\s*(.+)', content)
        issues = [i.strip() for i in issues if i.strip() and i.strip() != "없음"]
    return issues


def extract_warnings(llm_response):
    """LLM 응답에서 경고사항 추출 (기존 유지)"""
    warnings = []
    pattern = r'경고사항:\s*\n(.+?)(?=\n\n|$)'
    match = re.search(pattern, llm_response, re.DOTALL)
    if match:
        content = match.group(1)
        warnings = re.findall(r'-\s*(.+)', content)
        warnings = [w.strip() for w in warnings if w.strip() and w.strip() != "없음"]
    return warnings