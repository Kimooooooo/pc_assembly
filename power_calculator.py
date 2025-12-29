# power_calculator.py
import re

def parse_watt(value):
    """ '65W', '850W', '정격 700W' 등에서 숫자 추출 """
    if not value:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    
    # W 앞의 숫자 추출 (예: 850W -> 850)
    matches = re.findall(r'(\d+)\s*[Ww]', str(value))
    if matches:
        return max(int(m) for m in matches)
        
    # 만약 W가 없으면 그냥 숫자만이라도 찾음
    matches = re.findall(r'\d+', str(value))
    if matches:
        # 너무 작은 숫자는 전력이 아닐 확률 높음 (예: 4070의 4070)
        # 하지만 정격출력 컬럼값일 수 있으므로 사용
        return int(matches[0])
    return 0

def calculate_total_power(combo):
    """제품명 텍스트에서 소비전력 추정"""
    total = 0
    
    # CPU
    if 'CPU' in combo:
        name = combo['CPU'].get('제품명', '')
        if 'i9' in name or 'r9' in name or '7950' in name or '14900' in name: total += 250
        elif 'i7' in name or 'r7' in name or '7800x3d' in name or '14700' in name: total += 200
        elif 'i5' in name or 'r5' in name or '12400' in name or '5600' in name: total += 120
        else: total += 100 # 기본값
        
    # GPU
    if 'GPU' in combo:
        name = combo['GPU'].get('제품명', '')
        if '4090' in name: total += 450
        elif '4080' in name: total += 320
        elif '4070' in name: total += 220 # Ti/Super 포함 여유있게
        elif '4060' in name: total += 150
        elif '3060' in name: total += 170
        else: total += 150 # 기본값

    # 기타
    total += 60 # 보드, 램, 팬, SSD 등 여유분
    
    return total

def check_power_compatibility(combo):
    """파워 용량 적절성 평가"""
    total_load = calculate_total_power(combo)
    
    if '파워' not in combo:
        return {
            "충분함": False,
            "메시지": "파워 부품 정보가 없습니다."
        }
        
    power_str = combo['파워'].get('제품명', '')
    rated_power = parse_watt(power_str)
    
    if rated_power == 0:
        return {
            "충분함": False, # 0W면 확인 불가로 처리
            "메시지": f"파워 용량 확인 불가 (제품명: {power_str})"
        }
        
    # 4070이나 4070 Ti 같은 고사양 GPU일 경우 정격만 보고 넘어가면 안될 수 있음
    # 하지만 여기서는 단순 용량 비교
    
    if rated_power < total_load:
        return {
            "충분함": False,
            "메시지": f"파워 용량 부족: 예상 {total_load}W > 정격 {rated_power}W"
        }
        
    # 여유 마진 체크 (권장: 로드율 80% 이하)
    if rated_power < total_load * 1.2:
        return {
            "충분함": True,
            "메시지": f"파워 여유 부족 주의 (예상 {total_load}W / 정격 {rated_power}W)"
        }
        
    return {
        "충분함": True,
        "메시지": ""
    }