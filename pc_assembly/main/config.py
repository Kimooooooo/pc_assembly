"""
config.py — 환경변수 로더

민감한 값(API 키, DB 비밀번호, Django SECRET_KEY)은 .env 파일에 저장.
이 파일은 os.getenv()로만 읽는다 → 코드에 비밀 없음.

.env 파일은 .gitignore에 포함 → 절대 깃허브에 올리지 않음
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 파일 위치: <git_root>/pc_assembly/main/config.py
# .env 위치:  <git_root>/.env
_MAIN_DIR   = Path(__file__).parent       # .../main/
_DJANGO_DIR = _MAIN_DIR.parent            # .../pc_assembly/ (Django project)
GIT_ROOT    = _DJANGO_DIR.parent          # <git_root>

# .env를 git root 경로로 명시적 로드 (CWD에 상관없이 항상 찾음)
load_dotenv(GIT_ROOT / ".env")

# ── OpenAI API ───────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# 모델 변경 시 .env의 OPENAI_MODEL 값만 수정하면 됨
# 선택지: gpt-4o-mini | gpt-4.1-nano | gpt-4o | gpt-4.1
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── 임베딩 모델 ──────────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL",
    "dragonkue/snowflake-arctic-embed-l-v2.0-ko",
)
# HF 오프라인 모드: "1"=캐시만 사용(집 PC), "0"=첫 실행 시 자동 다운로드(새 PC)
HF_OFFLINE = os.getenv("HF_OFFLINE", "0")

# ── ChromaDB ────────────────────────────────────────────────────
# chroma_db 폴더는 git root에 있으므로 절대 경로로 지정
CHROMA_DIR        = os.getenv("CHROMA_DIR") or str(GIT_ROOT / "chroma_db")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "snowflake_arctic_ko")

# ── Django 민감 정보 (settings.py가 여기서 읽어 감) ─────────────
DJANGO_SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-me-in-dot-env",
)

# ── PostgreSQL (집 환경에서만 사용) ──────────────────────────────
# DB_NAME     = os.getenv("DB_NAME",     "pcdb")
# DB_USER     = os.getenv("DB_USER",     "pc")
# DB_PASSWORD = os.getenv("DB_PASSWORD", "")
# DB_HOST     = os.getenv("DB_HOST",     "localhost")
# DB_PORT     = os.getenv("DB_PORT",     "5433")
