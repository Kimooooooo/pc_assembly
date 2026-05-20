from dotenv import load_dotenv
import os

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SERPAPI_KEY    = os.getenv("SERPAPI_KEY", "")
