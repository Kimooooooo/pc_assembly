# compatibility.py
import re
from power_calculator import check_power_compatibility

# =========================================================
# 1. 좀비 파서 (텍스트에서 부품 정보 추출)
# =========================================================
def extract_parts_from_text(text):
    """
    LLM이 뱉은 견적 텍스트를 딕셔너리로 변환합니다.
    형식이 조금 깨지거나 특수문자가 있어도 핵심 키워드(CPU, 메인보드 등)를 찾아냅니다.
    """
    if isinstance(text, dict): return text
    
    parts = {}
    # (검색할 키워드, 표준 키)
    keywords_map = [
        ('CPU', 'CPU'),
        ('메인보드', 'MAINBORD'), ('MAINBOARD', 'MAINBORD'), ('M/B', 'MAINBORD'),
        ('RAM', 'RAM'), ('메모리', 'RAM'), ('램', 'RAM'),
        ('GPU', 'GPU'), ('그래픽카드', 'GPU'), ('VGA', 'GPU'),
        ('파워', 'POWER'), ('POWER', 'POWER'), ('PSU', 'POWER'),
        ('케이스', 'CASE'), ('CASE', 'CASE'),
        ('SSD', 'SSD'), ('쿨러', 'COOLER')
    ]

    lines = str(text).split('\n')
    for line in lines:
        line = line.strip()
        if not line or ':' not in line: continue
        
        # "키 : 값" 분리 (예: "▪️ 메인보드 : ASUS B650..." -> "메인보드", "ASUS B650...")
        key_part, val_part = line.split(':', 1)
        key_part = key_part.upper()
        
        # 키워드 매칭
        for kw, std_key in keywords_map:
            if kw in key_part:
                # 가격 정보 제거 (괄호 안의 원화 표시 삭제)
                # 예: "RTX 4070 (800,000원)" -> "RTX 4070"
                val_clean = re.sub(r'\([0-9,]+원?\).*', '', val_part).strip()
                val_clean = re.sub(r'\(\)', '', val_clean).strip() # 빈 괄호 제거
                
                # 딕셔너리에 저장
                parts[std_key] = {'제품명': val_clean, '상세정보': {}}
                
                # 편의를 위해 한글 키도 같이 넣어줌 (Power Calculator 호환용)
                if std_key == 'POWER': parts['파워'] = parts[std_key]
                break
    
    return parts

# =========================================================
# 2. 메인 체크 함수 (재판관)
# =========================================================
def check_compatibility(combo_input, openai_client=None):
    # 1. 파싱 (데이터 읽기)
    parts = extract_parts_from_text(combo_input)
    
    # 부품이 3개 미만이면 읽기 실패로 간주
    if len(parts) < 3:
        return {
            "호환됨": False, 
            "문제점": ["부품 목록을 읽을 수 없습니다. (파싱 실패)"], 
            "경고사항": [], 
            "결과_텍스트": "❌ 데이터 오류"
        }

    result = {"호환됨": True, "문제점": [], "경고사항": []}

    # 2. 파워 용량 체크 (1교시에 만든 계산기 활용)
    if 'POWER' in parts or '파워' in parts:
        p_res = check_power_compatibility(parts)
        if not p_res['충분함']:
            result['호환됨'] = False
            result['문제점'].append(p_res['메시지'])
        elif p_res['메시지']: # 충분하지만 여유가 적을 때
            result['경고사항'].append(p_res['메시지'])
    else:
        result['경고사항'].append("파워 정보가 없어 전력 계산을 건너뜁니다.")

    # 3. CPU <-> 메인보드 소켓 체크 (가장 중요!)
    cpu_name = normalize(parts.get('CPU', {}).get('제품명', ''))
    mb_name = normalize(parts.get('MAINBORD', {}).get('제품명', ''))
    
    if cpu_name and mb_name:
        # [AMD AM5] 라이젠 7000번대 이상 (7500F, 7800X3D 등)
        if any(x in cpu_name for x in ['7500','7600','7700','7800','7900','7950','8500','8600','8700','9600','9700']):
            # AM5 보드(650, 670 등)가 아니면 불합격
            if not any(x in mb_name for x in ['B650','X670','A620','B850','X870']):
                # 확실히 AM4 보드인 경우 에러 처리
                if any(x in mb_name for x in ['B550','A520','X570','B450']):
                    result['호환됨'] = False
                    result['문제점'].append(f"🚨 소켓 불일치: 라이젠 7000번대 이상(AM5)은 {parts['MAINBORD']['제품명']}과 호환되지 않습니다.")

        # [AMD AM4] 라이젠 5000번대 (5600X, 5800X3D 등)
        elif any(x in cpu_name for x in ['5500','5600','5700','5800','5900','5950']):
            # AM5 보드를 쓰면 불합격
            if any(x in mb_name for x in ['A620','B650','X670']):
                result['호환됨'] = False
                result['문제점'].append(f"🚨 소켓 불일치: 라이젠 5000번대(AM4)는 신형 보드(AM5)에 꽂을 수 없습니다.")

        # [Intel] 12~14세대 (LGA1700)
        elif any(x in cpu_name for x in ['12100','12400','12600','12700','12900','13100','13400','13600','13700','13900','14100','14400','14600','14700','14900']):
            # LGA1700 보드가 아니면 경고 (600, 700번대 칩셋)
            if not any(x in mb_name for x in ['H610','B660','H670','Z690','B760','H770','Z790']):
                 if any(x in mb_name for x in ['H510','B560','Z590','H410','B460']):
                    result['호환됨'] = False
                    result['문제점'].append("🚨 소켓 불일치: 인텔 12~14세대는 LGA1700 소켓 메인보드가 필요합니다.")

    # 4. RAM 규격 체크 (DDR4 vs DDR5)
    ram_name = normalize(parts.get('RAM', {}).get('제품명', ''))
    if mb_name and ram_name:
        if 'DDR5' in mb_name and 'DDR4' in ram_name:
            result['호환됨'] = False
            result['문제점'].append("🚨 규격 불일치: DDR5 전용 메인보드에 DDR4 램을 꽂을 수 없습니다.")
        elif 'DDR4' in mb_name and 'DDR5' in ram_name:
            result['호환됨'] = False
            result['문제점'].append("🚨 규격 불일치: DDR4 전용 메인보드에 DDR5 램을 꽂을 수 없습니다.")

    result['결과_텍스트'] = "✅ 호환성 확인 완료" if result['호환됨'] else "❌ 호환성 문제 발견"
    return result

def normalize(text):
    """비교를 위해 문자열 정리 (대문자 변환, 공백/하이픈 제거)"""
    return text.upper().replace(" ", "").replace("-", "")