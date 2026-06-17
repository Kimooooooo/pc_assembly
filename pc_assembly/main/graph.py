"""
graph.py — PC 견적 추천 LangGraph 파이프라인

실행 흐름:
  START
    ↓
  analyze_request   # OpenAI: 사용자 입력 → 검색 키워드 JSON
    ↓
  search_parts      # ChromaDB: 카테고리 필터 검색 → 후보 부품 수집
    ↓
  generate_quotes   # OpenAI: 후보 부품 → 견적 5세트 JSON
    ↓
  check_compatibility  # JSON 룰 기반 소켓/DDR/전력 검증
    ↓
  [조건부 엣지] 호환 견적 0개 + 재시도 < 2회 → generate_quotes 재시도
    ↓
  filter_and_format    # 최대 3개 선별 + image_url 매핑 + 최종 포맷
    ↓
  END
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TypedDict

import certifi
import chromadb
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from sentence_transformers import SentenceTransformer

from .compatibility import check_compat_meta
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()
os.environ["SSL_CERT_FILE"]      = certifi.where()

from .config import (
    CHROMA_COLLECTION,
    CHROMA_DIR,
    EMBEDDING_MODEL,
    HF_OFFLINE,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

# HF_OFFLINE=1 이면 캐시만 사용 (집 PC / 이미 다운로드된 환경)
# HF_OFFLINE=0 이면 첫 실행 시 자동 다운로드 허용 (새 PC)
if HF_OFFLINE == "1":
    os.environ["HF_HUB_OFFLINE"]      = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

# ══════════════════════════════════════════════════════════════════
# GraphState 정의
# ══════════════════════════════════════════════════════════════════
class GraphState(TypedDict):
    """
    LangGraph가 노드 간에 공유하는 전체 상태(State) 정의.

    messages:
        Annotated[list, add_messages] 를 사용하면
        각 노드가 반환한 새 메시지가 기존 리스트에 '덮어쓰기' 대신 '누적(append)' 된다.
        → 파이프라인 전 단계의 진행 로그를 messages 하나로 추적 가능.

    나머지 필드:
        노드가 반환한 dict의 키가 state의 키와 같으면 해당 값이 교체(replace)된다.
        (add_messages 같은 reducer 없이는 항상 마지막 값으로 덮어씀)
    """

    # ── 진행 로그 (누적) ─────────────────────────────────────────
    messages: Annotated[list, add_messages]

    # ── 사용자 입력 (진입점에서 설정) ────────────────────────────
    budget:  int    # 총 예산 (원)
    purpose: str    # 사용 목적 (게이밍, 영상편집, 문서작업 등)
    notes:   str    # 추가 요구사항 (조용한 쿨러, 화이트 케이스 등)

    # ── 파이프라인 중간 상태 ──────────────────────────────────────
    keywords:   Dict[str, List[str]]          # {카테고리: [검색어, ...]}
    candidates: Dict[str, List[Dict[str, Any]]] # {카테고리: [{제품 정보 + 메타데이터}, ...]}
    raw_quotes: List[Dict[str, Any]]          # OpenAI가 생성한 견적 후보 (최대 5)
    valid_quotes: List[Dict[str, Any]]        # 호환성 통과 견적

    # ── 검색 필터 / 예산 배분 (tune_allocation 노드에서 설정) ───
    require_rgb:       bool              # LED/RGB 제품 필요 여부
    require_color:     str               # 케이스 색상 요구 ("white", "black", "")
    budget_allocation: Dict[str, float]  # 카테고리별 예산 배분 비율 (합 = 1.0)

    # ── 흐름 제어 ────────────────────────────────────────────────
    retry_count:        int         # generate_quotes 재시도 횟수
    search_retry_count: int         # search_parts 재시도 횟수 (최대 2)
    failed_parts:       List[str]   # 호환성 실패 견적에 포함된 제품명 목록
                                    # → search_parts 재시도 시 이 제품들을 제외하고 새 후보 탐색
    compat_failure_hints: List[str] # 이전 호환성 실패 이유 목록
                                    # → generate_quotes 재시도 시 프롬프트에 포함해 같은 실수 방지
    error: Optional[str]            # 노드 내 오류 메시지


# ══════════════════════════════════════════════════════════════════
# 공유 리소스 — Lazy 초기화 (첫 요청 시 1회만 실행)
# ══════════════════════════════════════════════════════════════════
# 모듈 로드 시점(Django 시작)에 실행하면 임베딩 모델/DB 로드로 서버 시작이 느려지고,
# 경로 오류 시 Django 자체가 뜨지 않는 문제가 생긴다.
# 대신 첫 API 요청 때 한 번만 초기화한다.

_chroma_client = None
_collection    = None
_embed_model   = None
_llm           = None

_QUERY_PROMPT = "Represent this sentence for searching relevant passages: "

# ── 용도별 기본 예산 배분 비율 ─────────────────────────────────────
# 새 하드웨어 세대가 나와도 비율은 바뀌지 않으므로 하드코딩이 적절함
_DEFAULT_ALLOC: Dict[str, Dict[str, float]] = {
    "gaming": {"GPU": 0.38, "CPU": 0.18, "RAM": 0.07, "SSD": 0.10,
               "메인보드": 0.10, "파워": 0.05, "케이스": 0.07, "쿨러": 0.05},
    "office": {"GPU": 0.10, "CPU": 0.25, "RAM": 0.10, "SSD": 0.15,
               "메인보드": 0.18, "파워": 0.08, "케이스": 0.09, "쿨러": 0.05},
    "video":  {"GPU": 0.30, "CPU": 0.25, "RAM": 0.13, "SSD": 0.12,
               "메인보드": 0.10, "파워": 0.05, "케이스": 0.03, "쿨러": 0.02},
    "ai":     {"GPU": 0.50, "CPU": 0.15, "RAM": 0.12, "SSD": 0.10,
               "메인보드": 0.07, "파워": 0.04, "케이스": 0.01, "쿨러": 0.01},
    "design": {"GPU": 0.35, "CPU": 0.22, "RAM": 0.12, "SSD": 0.12,
               "메인보드": 0.10, "파워": 0.05, "케이스": 0.03, "쿨러": 0.01},
    "general":{"GPU": 0.28, "CPU": 0.22, "RAM": 0.10, "SSD": 0.12,
               "메인보드": 0.12, "파워": 0.07, "케이스": 0.06, "쿨러": 0.03},
}



def _get_collection():
    """ChromaDB 컬렉션 — 최초 호출 시 초기화"""
    global _chroma_client, _collection
    if _collection is None:
        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_DIR,
            settings=chromadb.Settings(anonymized_telemetry=False),
        )
        _collection = _chroma_client.get_collection(CHROMA_COLLECTION)
    return _collection


def _get_embed_model():
    """임베딩 모델 — 최초 호출 시 로드 (캐시 없으면 자동 다운로드)"""
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer(
            EMBEDDING_MODEL, device="cpu"
        )
    return _embed_model


def _get_llm():
    """OpenAI LLM 클라이언트 — 최초 호출 시 생성"""
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            api_key=OPENAI_API_KEY,
            model=OPENAI_MODEL,
            temperature=0.3,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
    return _llm


# ══════════════════════════════════════════════════════════════════
# 유틸 함수
# ══════════════════════════════════════════════════════════════════

def _encode_query(text: str) -> list:
    """
    검색 쿼리를 ChromaDB용 임베딩 벡터로 변환.
    Snowflake 모델은 '문서용 임베딩'과 '쿼리용 임베딩'을 구분하므로
    쿼리 앞에 _QUERY_PROMPT를 붙여야 정확도가 올라간다.
    """
    return _get_embed_model().encode(
        [_QUERY_PROMPT + text],
        normalize_embeddings=True,
    ).tolist()




# ══════════════════════════════════════════════════════════════════
# Node 1: analyze_request
# ══════════════════════════════════════════════════════════════════

# 프론트엔드 purpose 값 → 한국어 + 하드웨어 우선순위 가이드
_PURPOSE_GUIDE: Dict[str, Dict[str, str]] = {
    "gaming": {
        "label": "게이밍 (고사양 게임)",
        "guide": "GPU를 최우선으로 선택하세요. CPU는 중상급 이상, RAM 16GB 이상 필수. "
                 "고프레임 게임에는 RTX 50시리즈 이상 GPU가 필요합니다.",
    },
    "office": {
        "label": "사무/문서 작업",
        "guide": "GPU는 내장그래픽이나 저가형으로 충분합니다. CPU 안정성과 발열 관리 우선, "
                 "SSD 필수, RAM 16GB면 충분합니다.",
    },
    "video": {
        "label": "영상편집/렌더링",
        "guide": "CPU와 GPU 둘 다 고성능이 필요합니다. RAM 32GB 이상, 빠른 NVMe SSD 필수. "
                 "렌더링 속도를 위해 멀티코어 CPU와 GPU VRAM 8GB 이상 권장.",
    },
    "ai": {
        "label": "AI/딥러닝/머신러닝",
        "guide": "GPU VRAM을 극대화하세요 (RTX 4080급 이상, 16GB VRAM 이상). "
                 "CPU는 데이터 로딩용 중상급, RAM 32GB 이상, 고속 SSD 필수.",
    },
    "design": {
        "label": "그래픽/디자인",
        "guide": "GPU 성능이 중요합니다 (렌더링, 3D 작업). CPU는 중상급, "
                 "RAM 32GB 권장, 대용량 SSD 필요.",
    },
    "general": {
        "label": "일반/복합 사용",
        "guide": "전체적으로 균형잡힌 구성. 특정 부품에 치우치지 않고 "
                 "CPU, GPU, RAM, SSD를 고르게 배분하세요.",
    },
}


def analyze_request(state: GraphState) -> dict:
    """
    [Node 1] 사용자 입력을 분석해 카테고리별 검색 키워드를 생성한다.

    - purpose 값(영어)을 한국어 + 하드웨어 가이드로 변환해 OpenAI에 전달
      → 'gaming'만 넘기는 것보다 구체적인 하드웨어 우선순위를 함께 전달하면
         LLM이 더 적합한 키워드를 생성한다.
    - notes(추가 요구사항)도 함께 반영
    - JSON 파싱 실패 시 폴백: 기본 키워드로 대체
    - 출력: keywords dict + messages 누적
    """
    budget  = state["budget"]
    purpose = state["purpose"]
    notes   = state["notes"]

    guide_info = _PURPOSE_GUIDE.get(purpose, _PURPOSE_GUIDE["general"])
    purpose_ko = guide_info["label"]
    hw_guide   = guide_info["guide"]

    prompt = f"""
    사용자의 PC 견적 요청을 분석하여 각 카테고리별 검색 키워드를 JSON으로 생성하세요.

    예산: {budget:,}원
    주요 용도: {purpose_ko}
    하드웨어 우선순위: {hw_guide}
    추가 요구사항: {notes if notes else "없음"}

    지침:
    1. 예산과 목적에 맞는 실제 부품 검색어를 생성하세요
    2. 너무 고가의 부품을 추천하지 마세요 (예산 초과 방지)
    3. 추가 요구사항이 있으면 해당 카테고리 키워드에 반드시 반영하세요

    반드시 아래 JSON 형식으로만 답변하세요:
    {{
    "CPU": ["검색어"],
    "GPU": ["검색어"],
    "RAM": ["검색어"],
    "SSD": ["검색어"],
    "HDD": ["검색어"],
    "메인보드": ["검색어"],
    "파워": ["검색어"],
    "케이스": ["검색어"],
    "쿨러": ["검색어"]
    }}
    """

    response = _get_llm().invoke([HumanMessage(content=prompt)])

    try:
        keywords = json.loads(response.content)
    except (json.JSONDecodeError, AttributeError):
        keywords = {cat: [purpose_ko] for cat in
                    ["CPU", "GPU", "RAM", "SSD", "HDD", "메인보드", "파워", "케이스", "쿨러"]}

    return {
        "keywords": keywords,
        "messages": [AIMessage(
            content=f"[1/5] 요구사항 분석 완료 | 예산: {budget:,}원 | {purpose_ko}"
        )],
    }


# ══════════════════════════════════════════════════════════════════
# Node 1.5: tune_allocation
# ══════════════════════════════════════════════════════════════════

def tune_allocation(state: GraphState) -> dict:
    """
    [Node 1.5] 기본 예산 배분을 설정하고 참고사항 기반으로 조정한다.

    처리 흐름:
        notes 없음 → 기본값 반환 (LLM 없음)
        notes 있음 → LLM 1회 호출로 아래 3가지를 한번에 추출:
            require_rgb      : 빛나는/반짝이는/예쁜/삐까 등 맥락 포함 LED 요구
            require_color    : 케이스 색상 요구 ("white" | "black" | "")
            budget_allocation: 하드웨어 선호에 맞게 비율 조정 (불필요하면 기본값 유지)

    하드코딩 트리거 리스트 없이 LLM이 자유 텍스트에서 의도를 직접 판단한다.
    """
    notes   = state.get("notes", "").strip()
    purpose = state.get("purpose", "general")

    default_alloc = _DEFAULT_ALLOC.get(purpose, _DEFAULT_ALLOC["general"]).copy()

    # notes가 없으면 LLM 호출 없이 즉시 반환
    if not notes:
        return {
            "budget_allocation": default_alloc,
            "require_rgb":       False,
            "require_color":     "",
            "messages": [AIMessage(content="[1.5/5] 예산 배분 확정 (기본값)")],
        }

    # ── notes가 있으면 LLM이 3가지를 한번에 판단 ─────────────
    prompt = f"""사용자의 PC 견적 참고사항을 분석해 아래 JSON을 반환하세요.

참고사항: {notes}
용도: {state['purpose']}
기본 예산 배분: {json.dumps(default_alloc, ensure_ascii=False)}

판단 기준:
- require_rgb: 빛남/반짝임/LED/RGB/알록달록/예쁜/삐까/화려한 등 발광 요구면 true
- require_color: 케이스 색상 요구가 있으면 "white" 또는 "black", 없으면 ""
- budget_allocation: CPU/GPU 중요도 언급 등 하드웨어 선호가 있으면 비율 조정,
  없으면 기본값 그대로. 합계는 반드시 1.0.

반드시 아래 JSON 형식으로만 답변:
{{
  "require_rgb": true,
  "require_color": "white",
  "budget_allocation": {{"GPU": 0.38, "CPU": 0.18, "RAM": 0.07,
    "SSD": 0.10, "메인보드": 0.10, "파워": 0.05, "케이스": 0.07, "쿨러": 0.05}}
}}"""

    try:
        resp = _get_llm().invoke([HumanMessage(content=prompt)])
        data = json.loads(resp.content)

        require_rgb   = bool(data.get("require_rgb", False))
        require_color = str(data.get("require_color", ""))

        raw_alloc = data.get("budget_allocation", {})
        total     = sum(raw_alloc.values()) if raw_alloc else 0
        if total > 0:
            raw_alloc = {k: round(v / total, 3) for k, v in raw_alloc.items()}
        final_alloc = default_alloc.copy()
        final_alloc.update({k: v for k, v in raw_alloc.items() if k in default_alloc})

    except Exception:
        require_rgb   = False
        require_color = ""
        final_alloc   = default_alloc

    label = f"RGB: {require_rgb} | 색상: {require_color or '무관'}"
    return {
        "budget_allocation": final_alloc,
        "require_rgb":       require_rgb,
        "require_color":     require_color,
        "messages": [AIMessage(content=f"[1.5/5] 예산 배분 조정 완료 | {label}")],
    }


# ══════════════════════════════════════════════════════════════════
# Node 2: search_parts
# ══════════════════════════════════════════════════════════════════

def search_parts(state: GraphState) -> dict:
    """
    [Node 2] ChromaDB에서 카테고리별로 부품을 검색해 후보 목록을 만든다.

    개선 사항 (tune_allocation 연동):
    - budget_allocation 비율로 카테고리별 예산을 계산하고,
      그 ±범위(0.4~1.8배) 안에 드는 제품만 남긴다 → 고예산이면 고사양 제품이 후보에 들어옴
    - require_rgb=True면 RAM/케이스/쿨러를 has_rgb=true 제품으로 필터
    - require_color가 있으면 케이스를 해당 색상으로 필터
    - 필터 결과가 5개 미만이면 필터 없이 원본으로 폴백 (너무 엄격해서 후보 없는 상황 방지)
    """
    search_retry  = state.get("search_retry_count", 0)
    failed_parts  = set(state.get("failed_parts", []))
    budget        = state["budget"]
    alloc         = state.get("budget_allocation") or _DEFAULT_ALLOC.get(state["purpose"], _DEFAULT_ALLOC["general"])
    require_rgb   = state.get("require_rgb", False)
    require_color = state.get("require_color", "")

    n_results = 25 if search_retry > 0 else 15
    keep_top  = 30 if search_retry > 0 else 20

    CAT_MAP = {
        "CPU": "CPU", "GPU": "GPU", "RAM": "RAM",
        "SSD": "SSD", "HDD": "HDD", "메인보드": "메인보드",
        "파워": "파워", "케이스": "케이스", "쿨러": "쿨러",
    }

    # RGB/색상 필터가 적용될 카테고리
    _RGB_CATS   = {"RAM", "케이스", "쿨러"}
    _COLOR_CATS = {"케이스"}

    candidates: Dict[str, List[Dict]] = {}

    for cat_key, chroma_cat in CAT_MAP.items():
        keywords = state["keywords"].get(cat_key, [cat_key])
        seen: set = set()
        results: List[Dict] = []

        # ChromaDB where 필터 구성
        base_where = {"category": chroma_cat}
        if require_rgb and cat_key in _RGB_CATS:
            chroma_where = {"$and": [{"category": chroma_cat}, {"has_rgb": "true"}]}
        elif require_color and cat_key in _COLOR_CATS:
            chroma_where = {"$and": [{"category": chroma_cat}, {"color": require_color}]}
        else:
            chroma_where = base_where

        for kw in keywords:
            emb = _encode_query(kw)
            try:
                res = _get_collection().query(
                    query_embeddings=emb,
                    n_results=n_results,
                    where=chroma_where,
                    include=["metadatas", "distances"],
                )
            except Exception:
                # 필터 조건에 맞는 제품이 없으면 기본 검색으로 폴백
                res = _get_collection().query(
                    query_embeddings=emb,
                    n_results=n_results,
                    where=base_where,
                    include=["metadatas", "distances"],
                )

            for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
                name = meta.get("product_name", "")
                if not name or name in seen or name in failed_parts:
                    continue
                seen.add(name)
                # 기본 필드 + ChromaDB에 저장된 모든 메타데이터를 함께 보존
                item = {
                    "product_name": name,
                    "price":        meta.get("price", ""),
                    "image_url":    meta.get("image_url", ""),
                    "category":     chroma_cat,
                    "score":        round(1.0 - dist, 4),
                }
                item.update({k: v for k, v in meta.items()
                              if k not in ("product_name", "price", "image_url", "category")})
                results.append(item)

        # ── 가격 구간 필터 (budget_allocation 기반) ──────────────
        cat_budget    = budget * alloc.get(cat_key, 0.10)
        price_min     = cat_budget * 0.4
        price_max     = cat_budget * 1.8
        price_filtered = [
            r for r in results
            if price_min <= _parse_price_int(r["price"]) <= price_max
        ]
        # 5개 미만이면 폴백 (가격 분포가 기대와 다를 때)
        final = price_filtered if len(price_filtered) >= 5 else results
        candidates[cat_key] = sorted(final, key=lambda x: x["score"], reverse=True)[:keep_top]

    total = sum(len(v) for v in candidates.values())
    retry_label = f" (재검색 {search_retry}회차, 실패부품 {len(failed_parts)}개 제외)" if search_retry > 0 else ""
    return {
        "candidates":         candidates,
        "search_retry_count": search_retry + 1,
        "messages": [AIMessage(content=f"[2/5] 부품 후보 {total}개 수집{retry_label}")],
    }


# ══════════════════════════════════════════════════════════════════
# Node 3: generate_quotes
# ══════════════════════════════════════════════════════════════════

def generate_quotes(state: GraphState) -> dict:
    """
    [Node 3] 후보 부품 목록을 OpenAI에게 전달해 3가지 유형의 견적을 생성한다.

    출력 견적 3종 (예산 내에서 구성):
      - 가성비형: 예산의 ~70% 이내, 가격 대비 성능 극대화
      - 밸런스형: 예산의 ~85% 이내, 성능·가격 균형
      - 최고스펙형: 예산 한도까지 최대한 고성능 부품 사용

    - 입력: candidates, budget, purpose, retry_count
    - 후보 목록을 텍스트로 직렬화해 LLM 컨텍스트로 전달
      (각 카테고리 상위 10개만 전달 → 토큰 절약)
    - 재시도(retry) 시 "이전 호환성 실패" 힌트 추가 → 다른 조합 유도
    - JSON 파싱 실패 시 raw_quotes=[] 반환
    - 출력: raw_quotes + messages 누적
    """
    retry = state.get("retry_count", 0)
    hints = state.get("compat_failure_hints", [])

    retry_hint = ""
    if retry > 0:
        retry_hint = "\n주의: 이전에 생성한 견적이 호환성 검증에 실패했습니다. 다른 부품 조합을 시도하세요."
    if hints:
        retry_hint += (
            "\n\n⚠️ 반드시 피해야 할 이전 호환성 실패 원인:\n"
            + "\n".join(f"- {h}" for h in hints)
            + "\n위 문제를 일으킨 부품 조합을 피하고 호환되는 다른 부품을 선택하세요."
        )

    budget = state["budget"]

    # 각 유형별 예산 상한선 계산
    budget_value   = int(budget * 0.70)   # 가성비: 예산의 70%
    budget_balance = int(budget * 0.85)   # 밸런스: 예산의 85%
    budget_max     = budget               # 최고스펙: 예산 100%

    # 후보 목록 텍스트 직렬화 (카테고리별 상위 10개)
    candidates_text = ""
    for cat, items in state["candidates"].items():
        candidates_text += f"\n[{cat}]\n"
        for item in items[:10]:
            candidates_text += f"  - {item['product_name']} ({item['price']})\n"

    notes_text = state.get("notes", "")
    prompt = f"""
아래 부품 후보 목록에서 PC 견적 3가지를 JSON으로 생성하세요.
총 예산: {budget:,}원 | 목적: {state['purpose']}
사용자 요구사항: {notes_text}{retry_hint}

⚠️ 예산 상한 — 각 견적의 부품 가격 합계가 반드시 아래 금액 이하여야 합니다:
  견적1 (가성비형)  합계 ≤ {budget_value:,}원   ← 초과 시 더 저렴한 부품으로 교체
  견적2 (밸런스형)  합계 ≤ {budget_balance:,}원  ← 초과 시 더 저렴한 부품으로 교체
  견적3 (최고스펙형) 합계: {int(budget * 0.85):,}원 ~ {budget_max:,}원

공통 규칙:
- CPU, GPU, RAM, SSD, 메인보드, 파워, 케이스, 쿨러 8개 카테고리 모두 포함
- 부품 이름은 반드시 아래 후보 목록에 있는 제품명 그대로 사용 (목록에 없는 제품명 절대 사용 금지)
- price 필드는 후보 목록에 표시된 가격 그대로 사용

reason 작성 규칙 (3문장, 각 문장 구체적으로):
  1문장: 핵심 부품(CPU/GPU) 선정 근거 — 이 제품이 "{notes_text}" 조건에 맞는 이유
  2문장: 사용자 특별 요청 반영 내용 — RGB/색상/다중실행 등 요청 사항이 어떤 부품으로 충족됐는지
  3문장: 이 견적 유형의 성능·가격 포지셔닝 — 다른 견적 대비 장점

각 견적 JSON (id는 반드시 1, 2, 3):
{{"id": 1, "type": "가성비형",  "CPU": {{"name": "...", "price": "..."}}, "GPU": {{"name": "...", "price": "..."}}, "RAM": {{"name": "...", "price": "..."}}, "SSD": {{"name": "...", "price": "..."}}, "메인보드": {{"name": "...", "price": "..."}}, "파워": {{"name": "...", "price": "..."}}, "케이스": {{"name": "...", "price": "..."}}, "쿨러": {{"name": "...", "price": "..."}}, "description": "...", "reason": ["...", "...", "..."]}}
{{"id": 2, "type": "밸런스형",  ...동일 구조...}}
{{"id": 3, "type": "최고스펙형", ...동일 구조...}}

부품 후보:
{candidates_text}

반드시 아래 형식으로만 답변하세요:
{{"quotes": [견적1, 견적2, 견적3]}}
"""

    response = _get_llm().invoke([HumanMessage(content=prompt)])

    try:
        data = json.loads(response.content)
        raw_quotes = data.get("quotes", [])
    except (json.JSONDecodeError, AttributeError):
        raw_quotes = []

    return {
        "raw_quotes":   raw_quotes,
        "retry_count":  retry + 1,
        "messages": [AIMessage(
            content=f"[3/5] 견적 3종 생성 (가성비/밸런스/최고스펙) | 시도 {retry + 1}회"
        )],
    }


# ══════════════════════════════════════════════════════════════════
# Node 4: check_compatibility
# ══════════════════════════════════════════════════════════════════

def _llm_compat_check(quote: dict) -> dict:
    """
    메타데이터 신뢰도 < 0.6일 때 LLM으로 호환성 판단 (폴백).
    메타데이터가 불완전한 제품(새 세대, 데이터 미추출 등)에 대비한다.
    """
    parts_text = "\n".join(
        f"{cat}: {quote.get(cat, {}).get('name', '미선택')}"
        for cat in ["CPU", "GPU", "RAM", "SSD", "메인보드", "파워", "케이스", "쿨러"]
    )
    prompt = (
        "아래 PC 부품 조합의 하드웨어 호환성을 검증하세요.\n\n"
        f"{parts_text}\n\n"
        "검증 항목: ①CPU소켓↔메인보드소켓 ②CPU DDR↔RAM DDR ③파워 용량 충분 여부\n\n"
        '반드시 아래 JSON만 출력:\n{"호환됨": true, "문제점": [], "경고사항": []}'
    )
    try:
        resp = _get_llm().invoke([HumanMessage(content=prompt)])
        raw = resp.content.strip()
        # 마크다운 코드 펜스 제거
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        # 영문 키 → 한국어 키 폴백
        compatible = data.get("호환됨", data.get("compatible", data.get("is_compatible", None)))
        problems   = data.get("문제점",  data.get("problems",   data.get("issues",       [])))
        warnings   = data.get("경고사항", data.get("warnings",  []))
        if compatible is None:
            compatible = True
        ok = bool(compatible)
        return {
            "호환됨":   ok,
            "문제점":   problems if isinstance(problems, list) else [str(problems)],
            "경고사항": warnings if isinstance(warnings, list) else [],
            "결과_텍스트": "✅ 호환성 확인 (LLM폴백)" if ok else "❌ 호환성 문제 (LLM폴백)",
        }
    except Exception:
        return {
            "호환됨":   False,
            "문제점":   ["LLM 검증 실패 — 수동 확인 필요"],
            "경고사항": [],
            "결과_텍스트": "⚠️ 검증 불가 (파싱 오류)",
        }


_PART_CATS = ["CPU", "GPU", "RAM", "SSD", "메인보드", "파워", "케이스", "쿨러"]

def _validate_parts(quote: dict, candidates: dict) -> List[str]:
    """
    LLM이 후보 목록에 없는 제품을 환각(hallucination)했는지 검사한다.
    candidates에 없는 제품명을 사용한 카테고리 목록을 반환한다.
    """
    all_names = {
        item["product_name"]
        for items in candidates.values()
        for item in items
    }
    return [
        f"{cat}: {quote[cat]['name']}"
        for cat in _PART_CATS
        if cat in quote and isinstance(quote[cat], dict)
        and quote[cat].get("name") and quote[cat]["name"] not in all_names
    ]


def check_compatibility_node(state: GraphState) -> dict:
    """
    [Node 4] 각 견적에 대해 하드웨어 호환성을 하이브리드 방식으로 검증한다.

    1차: ChromaDB 메타데이터 기반 Python 체크 (check_compat_meta)
         → confidence (신뢰도) 계산:
           - 각 검증 항목(소켓/DDR/전력)에서 양쪽 데이터가 모두 있으면 신뢰 가능
           - 신뢰 가능한 항목 비율 = confidence (0.0 ~ 1.0)
    2차: confidence < 0.6 이면 LLM 폴백 (_llm_compat_check)
         → 메타데이터 불완전(새 세대 부품, 추출 실패 등) 시 대비

    실패 시 compat_failure_hints에 이유를 누적해 generate_quotes 재시도 프롬프트에 반영.
    """
    valid                = []
    failed_parts         = list(state.get("failed_parts", []))
    compat_failure_hints = list(state.get("compat_failure_hints", []))
    candidates           = state.get("candidates", {})
    llm_fallback_count   = 0

    for quote in state["raw_quotes"]:
        # ── 0. 환각 검증 (후보 목록에 없는 제품명 사용 여부) ─────────
        hallucinated = _validate_parts(quote, candidates)
        if hallucinated:
            hint = f"⛔ 후보 목록에 없는 제품 사용 (목록의 정확한 제품명 사용): {', '.join(hallucinated)}"
            if hint not in compat_failure_hints:
                compat_failure_hints.append(hint)
            for entry in hallucinated:
                name = entry.split(": ", 1)[-1]
                if name not in failed_parts:
                    failed_parts.append(name)
            continue  # 이 견적 스킵 (환각 부품이 있으면 호환성 검증 불필요)

        # ── 1. 메타데이터 기반 Python 체크 ───────────────────────────
        result = check_compat_meta(quote, candidates)

        # ── 2. 신뢰도 0.6 미만 → LLM 폴백 ───────────────────────────
        if result.get("confidence", 1.0) < 0.6:
            result = _llm_compat_check(quote)
            llm_fallback_count += 1

        if result.get("호환됨", False):
            quote["compat_warnings"] = result.get("경고사항", [])
            valid.append(quote)
        else:
            for problem in result.get("문제점", []):
                if problem not in compat_failure_hints:
                    compat_failure_hints.append(problem)
            for cat in _PART_CATS:
                name = quote.get(cat, {}).get("name", "")
                if name and name not in failed_parts:
                    failed_parts.append(name)

    method_label = f" (LLM폴백 {llm_fallback_count}건)" if llm_fallback_count else ""
    return {
        "valid_quotes":         valid,
        "failed_parts":         failed_parts,
        "compat_failure_hints": compat_failure_hints,
        "messages": [AIMessage(content=(
            f"[4/5] 호환성 검증{method_label} | "
            f"통과: {len(valid)}/{len(state['raw_quotes'])}개 "
            f"| 누적 실패 부품: {len(failed_parts)}개"
        ))],
    }


# ══════════════════════════════════════════════════════════════════
# 조건부 엣지: should_retry
# ══════════════════════════════════════════════════════════════════

def should_retry(state: GraphState) -> str:
    """
    check_compatibility 이후의 3-way 분기 조건.

    흐름:
      valid_quotes ≥ 1                                      → "continue"        (정상 완료)
      valid_quotes == 0, retry_count < 2                    → "retry_generate"  (Node3 재시도)
        └ generate_quotes에 compat_failure_hints 전달 → 같은 조합 반복 방지
      valid_quotes == 0, retry_count ≥ 2, search_retry < 2 → "retry_search"    (Node2 재시도)
        └ 부품 풀 자체가 호환 불가 → 새 후보 탐색
      모든 재시도 소진                                       → "continue"        (포기)

    재시도 우선순위:
      1. generate_quotes 재시도 (같은 후보 풀에서 다른 조합 선택, LLM 힌트 제공)
      2. search_parts 재시도   (failed_parts 제외한 완전히 새 후보 탐색)
      3. 포기 → filter_and_format (빈 결과보다 호환 미보장이지만 결과 반환이 나음)
    """
    no_valid     = len(state.get("valid_quotes", [])) == 0
    retry_count  = state.get("retry_count", 0)
    search_retry = state.get("search_retry_count", 0)

    if not no_valid:
        return "continue"
    if retry_count < 2:
        return "retry_generate"  # 1차: Node3 재시도 (실패 힌트 포함)
    if search_retry < 2:
        return "retry_search"    # 2차: Node2 재시도 (새 후보 탐색)
    return "continue"            # 재시도 한도 초과 → 포기


# ══════════════════════════════════════════════════════════════════
# Node 5: filter_and_format
# ══════════════════════════════════════════════════════════════════

def _parse_price_int(price_val) -> int:
    """가격 문자열/숫자를 정수로 변환. "850,000원" → 850000"""
    if isinstance(price_val, (int, float)):
        return int(price_val)
    digits = "".join(c for c in str(price_val) if c.isdigit())
    return int(digits) if digits else 0


def _calc_total_price(quote: dict) -> int:
    """LLM total_price를 신뢰하지 않고 부품 가격을 직접 합산"""
    return sum(
        _parse_price_int(quote.get(cat, {}).get("price", 0))
        for cat in ["CPU", "GPU", "RAM", "SSD", "메인보드", "파워", "케이스", "쿨러"]
        if isinstance(quote.get(cat), dict)
    )


def filter_and_format(state: GraphState) -> dict:
    """
    [Node 5] 검증된 견적 중 최대 3개를 선별하고 최종 출력 형식으로 정리한다.

    - 입력: valid_quotes (없으면 raw_quotes 폴백)
    - total_price는 LLM 값을 쓰지 않고 부품 가격을 직접 합산해 덮어씀
    - candidates에서 image_url을 역매핑해 각 부품에 추가
    - id 순(가성비→밸런스→최고스펙) 정렬 후 최대 3개 반환
    """
    quotes = state.get("valid_quotes") or state.get("raw_quotes", [])

    # id 기준 정렬 (1→2→3 순서 보장)
    quotes_sorted = sorted(quotes, key=lambda q: q.get("id", 99))
    final = quotes_sorted[:3]

    # candidates에서 제품명 → image_url 역매핑
    image_map: Dict[str, str] = {}
    for cat_items in state.get("candidates", {}).values():
        for item in cat_items:
            image_map[item["product_name"]] = item.get("image_url", "")

    budget = state["budget"]
    # id별 예산 상한 비율 (가성비 70%, 밸런스 85%, 최고스펙 100%)
    _budget_limits = {1: 0.70, 2: 0.85, 3: 1.00}

    for quote in final:
        # image_url 주입
        for cat in _PART_CATS:
            part = quote.get(cat, {})
            if isinstance(part, dict):
                part["image_url"] = image_map.get(part.get("name", ""), "")
        # total_price 직접 계산으로 덮어쓰기 (LLM 오류 방지)
        total = _calc_total_price(quote)
        quote["total_price"] = total
        # reason이 없거나 list가 아닌 경우 빈 리스트로 보정
        if not isinstance(quote.get("reason"), list):
            quote["reason"] = []
        # 예산 초과 경고 주입
        limit = int(budget * _budget_limits.get(quote.get("id", 99), 1.0))
        if total > limit:
            quote.setdefault("compat_warnings", []).append(
                f"⚠️ {quote.get('type', '')} 예산 상한 초과: {total:,}원 > {limit:,}원"
            )

    summary_lines = [
        f"  견적{q.get('id', i+1)}: {q.get('description', '')} | {q.get('total_price', 0):,}원"
        for i, q in enumerate(final)
    ]
    summary = "\n".join(summary_lines)

    return {
        "valid_quotes": final,
        "messages": [AIMessage(content=f"[5/5] 최종 견적 {len(final)}개\n{summary}")],
    }


# ══════════════════════════════════════════════════════════════════
# 그래프 조립
# ══════════════════════════════════════════════════════════════════

def build_graph() -> StateGraph:
    """
    노드와 엣지를 연결해 컴파일된 LangGraph 실행 객체를 반환한다.

    add_edge(A, B)        : A가 끝나면 항상 B 실행
    add_conditional_edges : 함수 반환값에 따라 다음 노드 선택
    """
    g = StateGraph(GraphState)

    # ── 노드 등록 ─────────────────────────────────────────────────
    g.add_node("analyze_request",     analyze_request)
    g.add_node("tune_allocation",     tune_allocation)   # 예산 배분 조정 노드
    g.add_node("search_parts",        search_parts)
    g.add_node("generate_quotes",     generate_quotes)
    g.add_node("check_compatibility", check_compatibility_node)
    g.add_node("filter_and_format",   filter_and_format)

    # ── 엣지 연결 (순차) ──────────────────────────────────────────
    g.add_edge(START,                  "analyze_request")
    g.add_edge("analyze_request",      "tune_allocation")  # 키워드 생성 → 배분 조정
    g.add_edge("tune_allocation",      "search_parts")     # 배분 확정 → 검색
    g.add_edge("search_parts",         "generate_quotes")
    g.add_edge("generate_quotes",      "check_compatibility")

    # ── 조건부 엣지 (호환성 실패 → 재시도) ───────────────────────
    # retry_generate: Node3 재시도 (같은 후보 풀, 실패 힌트 포함)
    # retry_search  : Node2 재시도 (실패 부품 제외 + 새 후보 탐색)
    # continue      : 성공 또는 재시도 한도 초과 → 최종 포맷
    g.add_conditional_edges(
        "check_compatibility",
        should_retry,
        {
            "retry_generate": "generate_quotes",   # 1차: Node3 재생성
            "retry_search":   "search_parts",      # 2차: Node2 재검색
            "continue":       "filter_and_format", # 성공/포기 → 최종 포맷
        },
    )

    g.add_edge("filter_and_format", END)

    return g.compile()


# 모듈 레벨에서 그래프 인스턴스 생성 (import하면 바로 사용 가능)
graph = build_graph()


# ══════════════════════════════════════════════════════════════════
# 공개 실행 함수
# ══════════════════════════════════════════════════════════════════

def run_quote_pipeline(
    budget: int,
    purpose: str,
    notes: str = "",
    on_status=None,
) -> dict:
    """
    LangGraph 파이프라인의 공개 진입점.

    매개변수:
        budget   : 총 예산 (원 단위, 예: 1_500_000)
        purpose  : 사용 목적 (예: "고사양 게이밍")
        notes    : 추가 요구사항 (예: "조용한 쿨러, 화이트 케이스")
        on_status: 진행 상태를 실시간으로 받을 콜백 함수 (Django SSE 연동용)

    반환:
        {
            "quotes": [...],   # 최대 3개 최종 견적
            "messages": [...], # 전체 진행 로그
        }
    """
    initial_state: GraphState = {
        "messages":           [HumanMessage(content=f"예산 {budget:,}원, {purpose}, {notes}")],
        "budget":             budget,
        "purpose":            purpose,
        "notes":              notes,
        "keywords":           {},
        "candidates":         {},
        "raw_quotes":         [],
        "valid_quotes":       [],
        "require_rgb":        False,
        "require_color":      "",
        "budget_allocation":  {},
        "retry_count":          0,
        "search_retry_count":   0,
        "failed_parts":         [],
        "compat_failure_hints": [],
        "error":                None,
    }

    # 스트리밍 모드: stream → invoke 이중 실행 버그 수정
    # (이전 코드는 stream과 invoke를 모두 실행해 파이프라인이 2번 돌았음)
    if on_status:
        final = None
        for step in graph.stream(initial_state):
            node_name      = list(step.keys())[0]
            state_snapshot = list(step.values())[0]
            msgs = state_snapshot.get("messages", [])
            if msgs:
                on_status(msgs[-1].content)
            final = state_snapshot
    else:
        final = graph.invoke(initial_state)

    result = {
        "quotes":   final.get("valid_quotes", []),
        "messages": [m.content for m in final.get("messages", [])],
    }

    # 실행마다 랭그래프.md 자동 업데이트
    _update_langgraph_md(result, budget, purpose)

    return result


# ══════════════════════════════════════════════════════════════════
# 랭그래프.md 자동 업데이트
# ══════════════════════════════════════════════════════════════════

def _update_langgraph_md(result: dict, budget: int, purpose: str) -> None:
    """
    파이프라인 실행 결과를 md모음/랭그래프.md 에 누적 기록한다.
    실행할 때마다 '실행 로그' 섹션에 한 블록씩 추가된다.
    """
    md_path = Path(__file__).parent / "md모음" / "랭그래프.md"
    if not md_path.exists():
        return  # 파일 없으면 skip (초기 생성은 별도)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_quotes = len(result.get("quotes", []))
    log_lines = [
        f"\n### {now}",
        f"- 예산: {budget:,}원 | 목적: {purpose}",
        f"- 최종 견적 수: {n_quotes}개",
        "- 진행 로그:",
    ]
    for msg in result.get("messages", []):
        log_lines.append(f"  - {msg}")

    with open(md_path, "a", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
