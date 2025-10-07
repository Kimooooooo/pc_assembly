# config.py

import os



# Google Search (SerpAPI) Key:
# 환경 변수 SERPAPI_KEY에서 로드합니다.
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "ddae228a18671788bb93c3a087cd9653e6c1715b5aacff3e290f74637774728f")

# OpenAI API Key:
# 환경 변수 OPENAI_API_KEY에서 로드합니다.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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")

# Hugging Face Token (Embedding Model, if used):
# 환경 변수 HF_TOKEN에서 로드합니다.
HF_TOKEN = os.getenv("HF_TOKEN", "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")

