"""
PC 부품 RAG — 벡터 DB 빌더

사전 조건: convert_to_text.py를 먼저 실행하여 가공데이터/임베딩/*.txt 생성
이 스크립트는 .txt 파일을 읽어 임베딩 → ChromaDB(chroma_db/) 저장

실행 방법: 아래 SELECTED_MODEL을 원하는 모델로 변경 후 ▷ 실행
"""

# ═══════════════════════════════════════════════════════════════
#  모델 선택 — 아래에서 하나만 주석 해제
# ═══════════════════════════════════════════════════════════════
SELECTED_MODEL = "snowflake-arctic-ko"   # ← 권장 (한국어 특화, 1024차원)
# SELECTED_MODEL = "pplx-embed-v1-4b"   #   고차원 (2560차원, 느림)
# SELECTED_MODEL = "pixie-rune-v1"       #   범용 (1024차원)
# ═══════════════════════════════════════════════════════════════

import sys
import time
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import numpy as np

try:
    import chromadb
except ImportError:
    print("chromadb 설치 필요: pip install chromadb")
    sys.exit(1)

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    print("sentence-transformers 설치 필요: pip install sentence-transformers")
    sys.exit(1)

try:
    import torch
    DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    DEVICE = "cpu"

BATCH_SIZE = 128 if DEVICE == "cuda" else 16   # GPU: 128, CPU: 16

# ─── 경로 ───
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "가공데이터"
EMBED_DIR  = DATA_DIR / "임베딩"
CHROMA_DIR = BASE_DIR / "chroma_db"
CHROMA_DIR.mkdir(exist_ok=True)

# ─── 모델 설정 ───
MODEL_CONFIGS = {
    "snowflake-arctic-ko": {
        "model_id": "dragonkue/snowflake-arctic-embed-l-v2.0-ko",
        "display_name": "Snowflake Arctic Embed L v2.0 KO",
        "trust_remote_code": False,
        "doc_prompt": None,
        "query_prompt": "Represent this sentence for searching relevant passages: ",
    },
    "pplx-embed-v1-4b": {
        "model_id": "perplexity-ai/pplx-embed-v1-4b",
        "display_name": "PPLX Embed v1 4B",
        "trust_remote_code": True,
        "doc_prompt": None,
        "query_prompt": None,
    },
    "pixie-rune-v1": {
        "model_id": "telepix/PIXIE-Rune-v1.0",
        "display_name": "PIXIE-Rune v1.0",
        "trust_remote_code": True,
        "doc_prompt": None,
        "query_prompt": None,
    },
}

# txt 파일명 → (메타데이터 category, 세부 표시명)
# category는 RAG 검색 시 필터로 사용하는 간단한 분류
TXT_CATEGORY_MAP = {
    "cpu_amd":      ("CPU",   "CPU (AMD)"),
    "cpu_intel":    ("CPU",   "CPU (인텔)"),
    "gpu_nvidia":   ("GPU",   "GPU (NVIDIA)"),
    "gpu_amd":      ("GPU",   "GPU (AMD)"),
    "ram":          ("RAM",   "RAM"),
    "ssd":          ("SSD",   "SSD"),
    "hdd":          ("HDD",   "HDD"),
    "mainboard":    ("메인보드", "메인보드"),
    "power":        ("파워",   "파워서플라이"),
    "case":         ("케이스",  "케이스"),
    "cooler_air":   ("쿨러",   "공랭 쿨러"),
    "cooler_water": ("쿨러",   "수랭 쿨러"),
}


def fmt_price(v) -> str:
    try:
        p = int(float(str(v).replace(",", "").replace("원", "").strip()))
        return f"{p:,}원"
    except Exception:
        return str(v)


def collection_name(model_key: str) -> str:
    return model_key.lower().replace("-", "_").replace(".", "_")


# ─── STEP 1: .txt 파일 로드 ───

def load_texts() -> Tuple[List[str], List[dict], List[str]]:
    print("\n" + "=" * 60)
    print("STEP 1 — 텍스트 파일 로드")
    print("=" * 60)

    if not EMBED_DIR.exists():
        print(f"  오류: {EMBED_DIR} 폴더가 없습니다.")
        print("  convert_to_text.py를 먼저 실행해주세요.")
        sys.exit(1)

    all_texts, all_metas, all_ids = [], [], []

    for stem, (cat_key, display_name) in TXT_CATEGORY_MAP.items():
        txt_path = EMBED_DIR / f"{stem}.txt"
        csv_path = DATA_DIR / f"{stem}.csv"

        if not txt_path.exists():
            print(f"  없음 (txt): {txt_path.name}  →  convert_to_text.py 실행 필요")
            continue
        if not csv_path.exists():
            print(f"  없음 (csv): {csv_path.name}")
            continue

        lines = txt_path.read_text(encoding="utf-8").splitlines()
        df    = pd.read_csv(csv_path, encoding="utf-8-sig")

        doc_prefix = stem.upper()  # e.g. CPU_AMD, GPU_NVIDIA (ID 충돌 방지용)
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            row = df.iloc[i] if i < len(df) else pd.Series()
            all_texts.append(line)
            all_metas.append({
                "category":     cat_key,       # 간단 분류: CPU, GPU, RAM ...
                "display_name": display_name,  # 세부 분류: CPU (AMD), GPU (NVIDIA) ...
                "product_name": str(row.get("제품명", "알 수 없음")),
                "price":        fmt_price(str(row.get("가격", "0"))),
                "image_url":    str(row.get("이미지URL", "")),
            })
            all_ids.append(f"{doc_prefix}_{i}")

        print(f"  [{display_name:12}]  {len(lines):5}개")

    print(f"\n  합계: {len(all_texts):,}개")
    return all_texts, all_metas, all_ids


# ─── STEP 2: 임베딩 ───

def embed_texts(model: SentenceTransformer, texts: List[str],
                model_key: str, batch_size: int = 16) -> np.ndarray:
    cfg = MODEL_CONFIGS[model_key]
    doc_prompt = cfg.get("doc_prompt")
    inputs = [doc_prompt + t for t in texts] if doc_prompt else texts
    return model.encode(
        inputs,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )


# ─── STEP 3: ChromaDB 저장 ───

def build_chroma(model_key: str, texts: List[str], metas: List[dict],
                 ids: List[str], embeddings: np.ndarray,
                 chroma_batch: int = 500) -> None:
    print(f"\n  ChromaDB 저장 중 → {CHROMA_DIR}")
    client   = chromadb.PersistentClient(path=str(CHROMA_DIR))
    coll_name = collection_name(model_key)

    try:
        client.delete_collection(coll_name)
        print(f"  기존 컬렉션 삭제: {coll_name}")
    except Exception:
        pass

    coll = client.create_collection(name=coll_name, metadata={"hnsw:space": "cosine"})

    for i in range(0, len(texts), chroma_batch):
        j = min(i + chroma_batch, len(texts))
        coll.add(
            ids=ids[i:j],
            documents=texts[i:j],
            embeddings=embeddings[i:j].tolist(),
            metadatas=metas[i:j],
        )
        print(f"  저장 진행: {j:,} / {len(texts):,}", end="\r")

    print(f"\n  완료: [{coll_name}] {coll.count():,}개 저장")


# ─── 메인 ───

def main():
    if SELECTED_MODEL not in MODEL_CONFIGS:
        print(f"알 수 없는 모델: {SELECTED_MODEL}")
        print(f"선택 가능: {list(MODEL_CONFIGS.keys())}")
        return

    cfg = MODEL_CONFIGS[SELECTED_MODEL]
    print("=" * 60)
    print("PC 부품 벡터 DB 빌더")
    print(f"  모델   : {cfg['display_name']}")
    print(f"  HF ID  : {cfg['model_id']}")
    print(f"  디바이스: {DEVICE.upper()}")
    print(f"  저장   : {CHROMA_DIR}")
    print("=" * 60)

    # STEP 1
    texts, metas, ids = load_texts()

    # STEP 2
    print(f"\n{'=' * 60}")
    print(f"STEP 2 — 임베딩 ({len(texts):,}개, device={DEVICE})")
    print("=" * 60)
    print(f"  모델 로딩: {cfg['model_id']}")
    model = SentenceTransformer(
        cfg["model_id"],
        trust_remote_code=cfg.get("trust_remote_code", False),
        device=DEVICE,
    )
    dim = model.get_sentence_embedding_dimension()
    print(f"  로드 완료 (차원: {dim})")

    t0 = time.time()
    embeddings = embed_texts(model, texts, SELECTED_MODEL, batch_size=BATCH_SIZE)
    elapsed = round(time.time() - t0, 1)
    print(f"  임베딩 완료: {elapsed}초")

    del model
    if DEVICE == "cuda":
        import torch as _t
        _t.cuda.empty_cache()

    # STEP 3
    print(f"\n{'=' * 60}")
    print("STEP 3 — ChromaDB 저장")
    print("=" * 60)
    build_chroma(SELECTED_MODEL, texts, metas, ids, embeddings)

    print("\n" + "=" * 60)
    print("빌드 완료")
    print(f"  모델    : {cfg['display_name']} ({dim}차원)")
    print(f"  총 제품 : {len(texts):,}개")
    print(f"  임베딩  : {elapsed}초")
    print(f"  컬렉션  : {collection_name(SELECTED_MODEL)}")
    print(f"  저장 위치: {CHROMA_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
