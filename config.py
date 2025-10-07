# config.py

import os



# Google Search (SerpAPI) Key:
# 환경 변수 SERPAPI_KEY에서 로드합니다.
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "키")

# OpenAI API Key:
# 환경 변수 OPENAI_API_KEY에서 로드합니다.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "키")

# Hugging Face Token (Embedding Model, if used):
# 환경 변수 HF_TOKEN에서 로드합니다.
HF_TOKEN = os.getenv("HF_TOKEN", "키")

