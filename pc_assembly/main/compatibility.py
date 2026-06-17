# compatibility.py — ChromaDB 메타데이터 기반 호환성 검증
#
# 소켓·DDR·전력 정보는 vectordb.py 빌드 시 ChromaDB 메타데이터로 저장되며,
# check_compat_meta()가 candidates 딕셔너리에서 직접 읽어 검증한다.


def _find_meta(name: str, candidates: dict) -> dict:
    """candidates 딕셔너리에서 제품명으로 ChromaDB 메타데이터 검색"""
    for items in candidates.values():
        for item in items:
            if item.get("product_name") == name:
                return item
    return {}


def _safe_int(val) -> int:
    try:
        return int(val or 0)
    except (ValueError, TypeError):
        return 0


def _calc_confidence(cpu_meta: dict, mb_meta: dict, ram_meta: dict,
                     gpu_meta: dict, psu_meta: dict) -> float:
    """
    메타데이터 기반 호환성 체크의 신뢰도 계산 (0.0 ~ 1.0).
    각 검증 항목에서 양쪽 데이터가 모두 있으면 해당 항목은 신뢰 가능.
    신뢰 가능한 항목 비율 = confidence.

    0.6 미만이면 graph.py에서 LLM 폴백으로 전환한다.
    """
    def has(m: dict, k: str) -> bool:
        v = m.get(k, "")
        return bool(v) and v != "0"

    checks = [
        has(cpu_meta, "socket")    and has(mb_meta, "socket"),
        has(cpu_meta, "ddr_type")  and has(ram_meta, "ddr_type"),
        has(mb_meta,  "ddr_type")  and has(ram_meta, "ddr_type"),
        (has(gpu_meta, "tdp") or has(cpu_meta, "tdp")) and has(psu_meta, "wattage"),
        has(gpu_meta, "required_psu") and has(psu_meta, "wattage"),
    ]
    return round(sum(checks) / len(checks), 2)


def check_compat_meta(quote: dict, candidates: dict) -> dict:
    """
    ChromaDB 메타데이터(socket, ddr_type, tdp, wattage, required_psu)를 사용해
    견적의 하드웨어 호환성을 검증한다.

    검증 항목:
        1. CPU ↔ 메인보드 소켓 일치
        2. CPU ↔ RAM DDR 규격 일치
        3. 메인보드 ↔ RAM DDR 규격 이중 확인
        4. CPU TDP + GPU TDP → 파워 용량 충분 여부 (20% 마진)
        5. GPU 권장 파워 ↔ 파워 정격 출력
    """
    result: dict = {"호환됨": True, "문제점": [], "경고사항": []}

    cpu_meta = _find_meta(quote.get("CPU",    {}).get("name", ""), candidates)
    mb_meta  = _find_meta(quote.get("메인보드", {}).get("name", ""), candidates)
    ram_meta = _find_meta(quote.get("RAM",    {}).get("name", ""), candidates)
    gpu_meta = _find_meta(quote.get("GPU",    {}).get("name", ""), candidates)
    psu_meta = _find_meta(quote.get("파워",   {}).get("name", ""), candidates)

    result["confidence"] = _calc_confidence(cpu_meta, mb_meta, ram_meta, gpu_meta, psu_meta)

    # ── 1. CPU ↔ 메인보드 소켓 ──────────────────────────────────
    cpu_sock = cpu_meta.get("socket", "")
    mb_sock  = mb_meta.get("socket",  "")
    if cpu_sock and mb_sock:
        if cpu_sock != mb_sock:
            result["호환됨"] = False
            result["문제점"].append(
                f"🚨 소켓 불일치: CPU {cpu_sock} ↔ 메인보드 {mb_sock}"
            )
    elif cpu_sock and not mb_sock:
        result["경고사항"].append(
            f"⚠️ 메인보드 소켓 정보 없음 (CPU: {cpu_sock}) — 수동 확인 필요"
        )

    # ── 2. CPU ↔ RAM DDR ────────────────────────────────────────
    cpu_ddr = cpu_meta.get("ddr_type", "")
    ram_ddr = ram_meta.get("ddr_type", "")
    if cpu_ddr and ram_ddr and cpu_ddr != ram_ddr:
        result["호환됨"] = False
        result["문제점"].append(
            f"🚨 DDR 불일치: CPU 지원 {cpu_ddr} ↔ RAM {ram_ddr}"
        )

    # ── 3. 메인보드 ↔ RAM DDR (이중 확인) ───────────────────────
    mb_ddr = mb_meta.get("ddr_type", "")
    if mb_ddr and ram_ddr and mb_ddr != ram_ddr:
        result["호환됨"] = False
        result["문제점"].append(
            f"🚨 DDR 불일치: 메인보드 {mb_ddr} ↔ RAM {ram_ddr}"
        )

    # ── 4. 전력 체크 (CPU TDP + GPU TDP + 기본 80W, 20% 마진) ──
    gpu_tdp = _safe_int(gpu_meta.get("tdp"))
    cpu_tdp = _safe_int(cpu_meta.get("tdp"))
    psu_w   = _safe_int(psu_meta.get("wattage"))
    if gpu_tdp or cpu_tdp:
        total_load = gpu_tdp + cpu_tdp + 80
        required   = int(total_load * 1.2)
        if psu_w:
            if psu_w < total_load:
                result["호환됨"] = False
                result["문제점"].append(
                    f"🚨 파워 부족: 예상 소비 {total_load}W > 정격 {psu_w}W"
                )
            elif psu_w < required:
                result["경고사항"].append(
                    f"⚠️ 파워 여유 부족: 예상 {total_load}W / 정격 {psu_w}W (권장 {required}W 이상)"
                )

    # ── 5. GPU 권장 파워 체크 ────────────────────────────────────
    gpu_req = _safe_int(gpu_meta.get("required_psu"))
    if gpu_req and psu_w and psu_w < gpu_req:
        result["호환됨"] = False
        result["문제점"].append(
            f"🚨 GPU 권장 파워 미달: GPU 권장 {gpu_req}W ↔ 파워 {psu_w}W"
        )

    result["결과_텍스트"] = (
        "✅ 호환성 확인 완료" if result["호환됨"] else "❌ 호환성 문제 발견"
    )
    return result
