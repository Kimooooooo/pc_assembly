"""
PC 부품 RAG - 벡터 DB 빌더

사전 조건: convert_to_text.py를 먼저 실행하여 가공데이터/임베딩/*.txt 생성
이 스크립트는 .txt 파일을 읽어 임베딩 → ChromaDB(chroma_db/) 저장
"""

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

BATCH_SIZE = 128 if DEVICE == "cuda" else 16

# ─── 경로 ───
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "가공데이터"
EMBED_DIR  = DATA_DIR / "임베딩"
CHROMA_DIR = BASE_DIR / "chroma_db"
CHROMA_DIR.mkdir(exist_ok=True)

# ─── 모델 설정 (Snowflake Arctic Embed L v2.0 KO 고정) ───
MODEL_ID        = "dragonkue/snowflake-arctic-embed-l-v2.0-ko"
COLLECTION_NAME = "snowflake_arctic_ko"

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


# ─── 메타데이터 추출 ───

_RGB_KEYWORDS = {"RGB", "ARGB", "AURA", "MYSTIC LIGHT", "POLYCHROME", "PRISM", "FUSION", "RAINBOW"}

def _extract_rich_metadata(line: str, stem: str) -> dict:
    """
    TXT 한 줄(구조화 텍스트)에서 호환성·필터링용 메타데이터를 추출한다.
    ChromaDB 메타데이터로 저장되어 search_parts 필터링과 호환성 검증에 사용된다.

    추출 필드:
        CPU         : socket, ddr_type, tdp
        메인보드    : socket, ddr_type
        RAM         : ddr_type, capacity_gb, has_rgb
        GPU         : tdp, required_psu, vram_gb, has_rgb
        파워        : wattage, has_rgb
        케이스      : color, has_rgb
        쿨러        : supported_sockets, cooling_tdp, has_rgb
    """
    import re as _re

    def field(key: str) -> str:
        m = _re.search(rf'{_re.escape(key)}:\s*([^,\n]+)', line)
        return m.group(1).strip() if m else ""

    def parse_watt(s: str) -> str:
        m = _re.search(r'(\d+)\s*W', s)
        return m.group(1) if m else "0"

    def extract_ddr(s: str) -> str:
        m = _re.search(r'(DDR\d)', s)
        return m.group(1) if m else ""

    def extract_socket(s: str) -> str:
        m = _re.search(r'소켓(\w+)', s)
        if not m:
            return ""
        raw = m.group(1)
        return f"LGA{raw}" if raw.isdigit() else raw

    def detect_rgb(product_name: str) -> str:
        if "LED 라이트: ○" in line:
            return "true"
        name_up = product_name.upper()
        return "true" if any(kw in name_up for kw in _RGB_KEYWORDS) else "false"

    def detect_color(product_name: str) -> str:
        n = product_name.lower()
        if any(w in n for w in ("화이트", "white", "흰색")):
            return "white"
        if any(w in n for w in ("블랙", "black", "검은색")):
            return "black"
        if any(w in n for w in ("실버", "silver")):
            return "silver"
        return ""

    pname = field("제품명")
    meta: dict = {}

    if stem in ("cpu_amd", "cpu_intel"):
        meta["socket"]   = extract_socket(field("소켓 구분"))
        meta["ddr_type"] = extract_ddr(field("메모리 규격")) or extract_ddr(line)
        raw_tdp = field("TDP")
        meta["tdp"]      = parse_watt(raw_tdp) if raw_tdp else "0"

    elif stem == "mainboard":
        meta["socket"]   = extract_socket(field("CPU 소켓"))
        meta["ddr_type"] = extract_ddr(field("메모리 종류")) or extract_ddr(line)

    elif stem == "ram":
        meta["ddr_type"]    = extract_ddr(pname) or extract_ddr(line)
        cap = field("메모리 용량")
        m   = _re.search(r'(\d+)GB', cap)
        meta["capacity_gb"] = m.group(1) if m else "0"
        meta["has_rgb"]     = detect_rgb(pname)

    elif stem in ("gpu_nvidia", "gpu_amd"):
        meta["required_psu"] = parse_watt(field("권장 파워용량"))
        meta["tdp"]          = parse_watt(field("사용전력"))
        vram = field("메모리 용량")
        m    = _re.search(r'(\d+)GB', vram)
        meta["vram_gb"]      = m.group(1) if m else "0"
        meta["has_rgb"]      = detect_rgb(pname)

    elif stem == "power":
        meta["wattage"] = parse_watt(field("정격출력"))
        meta["has_rgb"] = detect_rgb(pname)

    elif stem == "case":
        meta["color"]   = detect_color(pname)
        meta["has_rgb"] = detect_rgb(pname)

    elif stem in ("cooler_air", "cooler_water"):
        sockets = [s for s in ("LGA1851", "LGA1700", "AM5", "AM4") if f"{s}: ○" in line]
        meta["supported_sockets"] = ",".join(sockets)
        meta["cooling_tdp"]       = parse_watt(field("TDP"))
        meta["has_rgb"]           = detect_rgb(pname)

    return meta


# ─── STEP 1: .txt 파일 로드 ───

def load_texts() -> Tuple[List[str], List[dict], List[str]]:
    print("\n" + "=" * 60)
    print("STEP 1 - 텍스트 파일 로드")
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

        doc_prefix = stem.upper()
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            row = df.iloc[i] if i < len(df) else pd.Series()
            all_texts.append(line)
            base_meta = {
                "category":     cat_key,
                "display_name": display_name,
                "product_name": str(row.get("제품명", "알 수 없음")),
                "price":        fmt_price(str(row.get("가격", "0"))),
                "image_url":    str(row.get("이미지URL", "")),
            }
            base_meta.update(_extract_rich_metadata(line, stem))
            all_metas.append(base_meta)
            all_ids.append(f"{doc_prefix}_{i}")

        print(f"  [{display_name:12}]  {len(lines):5}개")

    print(f"\n  합계: {len(all_texts):,}개")
    return all_texts, all_metas, all_ids


# ─── STEP 2: 임베딩 ───

def embed_texts(model: SentenceTransformer, texts: List[str],
                batch_size: int = 16) -> np.ndarray:
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )


# ─── STEP 3: ChromaDB 저장 ───

def build_chroma(texts: List[str], metas: List[dict],
                 ids: List[str], embeddings: np.ndarray,
                 chroma_batch: int = 500) -> None:
    print(f"\n  ChromaDB 저장 중 → {CHROMA_DIR}")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"  기존 컬렉션 삭제: {COLLECTION_NAME}")
    except Exception:
        pass

    coll = client.create_collection(name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"})

    for i in range(0, len(texts), chroma_batch):
        j = min(i + chroma_batch, len(texts))
        coll.add(
            ids=ids[i:j],
            documents=texts[i:j],
            embeddings=embeddings[i:j].tolist(),
            metadatas=metas[i:j],
        )
        print(f"  저장 진행: {j:,} / {len(texts):,}", end="\r")

    print(f"\n  완료: [{COLLECTION_NAME}] {coll.count():,}개 저장")


# ─── 메인 ───

def main():
    print("=" * 60)
    print("PC 부품 벡터 DB 빌더")
    print(f"  모델   : Snowflake Arctic Embed L v2.0 KO")
    print(f"  HF ID  : {MODEL_ID}")
    print(f"  디바이스: {DEVICE.upper()}")
    print(f"  저장   : {CHROMA_DIR}")
    print("=" * 60)

    # STEP 1
    texts, metas, ids = load_texts()

    # STEP 2
    print(f"\n{'=' * 60}")
    print(f"STEP 2 - 임베딩 ({len(texts):,}개, device={DEVICE})")
    print("=" * 60)
    print(f"  모델 로딩: {MODEL_ID}")
    model = SentenceTransformer(MODEL_ID, device=DEVICE)
    dim   = model.get_sentence_embedding_dimension()
    print(f"  로드 완료 (차원: {dim})")

    t0 = time.time()
    embeddings = embed_texts(model, texts, batch_size=BATCH_SIZE)
    elapsed = round(time.time() - t0, 1)
    print(f"  임베딩 완료: {elapsed}초")

    del model
    if DEVICE == "cuda":
        import torch as _t
        _t.cuda.empty_cache()

    # STEP 3
    print(f"\n{'=' * 60}")
    print("STEP 3 - ChromaDB 저장")
    print("=" * 60)
    build_chroma(texts, metas, ids, embeddings)

    print("\n" + "=" * 60)
    print("빌드 완료")
    print(f"  모델    : Snowflake Arctic Embed L v2.0 KO ({dim}차원)")
    print(f"  총 제품 : {len(texts):,}개")
    print(f"  임베딩  : {elapsed}초")
    print(f"  컬렉션  : {COLLECTION_NAME}")
    print(f"  저장 위치: {CHROMA_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
