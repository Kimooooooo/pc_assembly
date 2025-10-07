# power_calculator.py

import re

def parse_power_value(power_str):
    """
    전력 관련 문자열에서 최대 W 값을 추출 (예: '125-159W' -> 159, '162W' -> 162)
    """
    if not power_str:
        return 0
    
    # 여러 값이 있을 경우 가장 큰 값 선택 (PBP-MTP 같은 경우)
    matches = re.findall(r'(\d+)', power_str)
    if matches:
        return max([int(m) for m in matches])
    return 0


def get_max_power_consumption(component_data, category):
    """
    부품별 최대 소비 전력 추출 (추정 대신 상세정보 사용)
    
    Args:
        component_data: 부품 정보 딕셔너리 (상세정보가 파싱된 상태)
        category: 부품 카테고리
    
    Returns:
        최대 예상 소비 전력 (W)
    """
    
    details = component_data.get('상세정보', {})
    
    if category == 'CPU':
        # AMD: PPT, Intel: PBP-MTP 또는 MTP
        ppt = details.get('PPT')
        pbp_mtp = details.get('PBP-MTP') or details.get('MTP')
        
        if ppt:
            return parse_power_value(ppt)
        elif pbp_mtp:
            return parse_power_value(pbp_mtp)
        
        # fallback: 제품명으로 추정 (최후의 수단)
        return estimate_from_name(component_data.get('제품명', ''))

    elif category == 'GPU':
        # GPU는 사용전력 필드 사용
        power_str = details.get('사용전력')
        if power_str:
            return parse_power_value(power_str)
        
        # fallback: 권장파워 역산 또는 제품명 추정 (최후의 수단)
        recommended = parse_power_value(component_data.get('권장파워', ''))
        if recommended:
            return max(int(recommended * 0.8 - 235), 100) # 기존 역산 공식 유지
        
        return estimate_from_name(component_data.get('제품명', ''))

    # 기타 부품은 0으로 가정 (total_power에서 고정값으로 처리)
    return 0


def estimate_from_name(product_name):
    """제품명으로 대략적 추정 (최후의 수단, 기존 로직 유지)"""
    name_upper = product_name.upper()
    
    if "4090" in name_upper: return 450
    elif "4080" in name_upper: return 320
    elif "4070 TI" in name_upper: return 285
    elif "4070" in name_upper: return 200
    elif "4060" in name_upper: return 160
    elif "7800X3D" in name_upper: return 160
    elif "14900K" in name_upper: return 253
    elif "14700K" in name_upper: return 253
    elif "13600K" in name_upper: return 181
    return 100


def calculate_total_power(parts_combo):
    """
    전체 조합의 소비 전력 계산
    
    Args:
        parts_combo: 부품 조합 딕셔너리 (상세정보 포함)
    
    Returns:
        총 예상 소비 전력 (W)
    """
    
    total_power = 0
    
    # CPU 전력
    if 'CPU' in parts_combo:
        cpu_power = get_max_power_consumption(parts_combo['CPU'], 'CPU')
        total_power += cpu_power
    
    # GPU 전력
    if 'GPU' in parts_combo:
        gpu_power = get_max_power_consumption(parts_combo['GPU'], 'GPU')
        total_power += gpu_power
    
    # 기타 부품 고정값
    other_power = 85  # 메인보드 50 + RAM 10 + SSD 5 + 기타 20
    total_power += other_power
    
    return total_power


def check_power_compatibility(parts_combo):
    """파워 용량 충분한지 체크"""
    
    total_consumption = calculate_total_power(parts_combo)
    
    if '파워' not in parts_combo:
        return {
            "충분함": False,
            "총소비": total_consumption,
            "파워용량": 0,
            "안전용량": 0,
            "여유율": 0,
            "메시지": "파워 정보 없음"
        }
    
    power_name = parts_combo['파워']['제품명']
    
    # 파워 용량 추출 (예: '마이크로닉스 850W' -> 850)
    match = re.search(r'(\d+)\s*W', power_name)
    if not match:
        return {
            "충분함": False,
            "총소비": total_consumption,
            "파워용량": 0,
            "안전용량": 0,
            "여유율": 0,
            "메시지": "파워 용량 파싱 실패"
        }
    
    power_capacity = int(match.group(1))
    safe_capacity = power_capacity * 0.8
    
    margin_percent = ((safe_capacity - total_consumption) / safe_capacity) * 100 if safe_capacity > 0 else 0
    
    is_sufficient = total_consumption <= safe_capacity
    
    return {
        "충분함": is_sufficient,
        "총소비": total_consumption,
        "파워용량": power_capacity,
        "안전용량": int(safe_capacity),
        "여유율": round(margin_percent, 1),
        "메시지": get_power_message(is_sufficient, margin_percent)
    }


def get_power_message(is_sufficient, margin):
    """파워 상태 메시지"""
    if not is_sufficient:
        return "⚠️ 파워 용량 부족 - 더 높은 용량 필요"
    elif margin < 10:
        return "⚠️ 파워 여유 매우 적음 - 업그레이드 권장"
    elif margin < 20:
        return "✓ 파워 충분하나 여유 적음"
    else:
        return "✓ 파워 충분"


if __name__ == "__main__":
    
    # 테스트 조합 (GPU 450W, CPU 162W 가정)
    test_combo = {
        "CPU": {
            "제품명": "AMD 라이젠7 7800X3D",
            "가격": 453000,
            "상세정보": {"PPT": "162W"}
        },
        "GPU": {
            "제품명": "GIGABYTE 지포스 RTX 4090",
            "권장파워": "정격파워 1000W 이상",
            "가격": 2500000,
            "상세정보": {"사용전력": "450W"}
        },
        "파워": {
            "제품명": "마이크로닉스 850W",
            "가격": 79000,
        }
    }
    
    print("="*50)
    print("전력 호환성 체크 (개선 버전)")
    print("="*50)
    
    result = check_power_compatibility(test_combo)
    
    print(f"\n결과:")
    print(f"  총 소비: {result['총소비']}W")
    print(f"  파워 용량: {result['파워용량']}W")
    print(f"  안전 용량: {result['안전용량']}W (80% 기준)")
    print(f"  여유율: {result['여유율']}%")
    print(f"  {result['메시지']}")
    print(f"  충분함: {result['충분함']}")