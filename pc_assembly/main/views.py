"""
views.py — Django 뷰

GET  /          → index.html
POST /api/quote/ → LangGraph 파이프라인 실행, JSON 반환
"""

import json
import traceback
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


def index(request):
    return render(request, "main/index.html")


@csrf_exempt
@require_http_methods(["POST"])
def generate_quote(request):
    """
    POST /api/quote/
    body: { "budget": 1500000, "purpose": "gaming", "notes": "..." }

    LangGraph 파이프라인 실행 후 3종 견적 반환.
    에러 시 500 대신 명확한 JSON 오류 메시지 반환.
    """
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "JSON 파싱 실패"}, status=400)

    budget  = int(body.get("budget", 0))
    purpose = body.get("purpose", "general")
    notes   = body.get("notes",   "")

    if budget < 300_000:
        return JsonResponse({"error": "예산이 너무 낮습니다 (최소 30만원)"}, status=400)

    try:
        from .graph import run_quote_pipeline
        result = run_quote_pipeline(budget=budget, purpose=purpose, notes=notes)
        return JsonResponse(result, json_dumps_params={"ensure_ascii": False})

    except Exception as e:
        traceback.print_exc()
        err_str = str(e)

        # OpenAI 인증 오류
        if "AuthenticationError" in err_str or "Incorrect API key" in err_str or "401" in err_str:
            return JsonResponse(
                {"error": "OpenAI API 키가 올바르지 않습니다. .env 파일의 OPENAI_API_KEY를 확인해 주세요."},
                status=503,
            )
        # OpenAI 네트워크/연결 오류
        if "APIConnectionError" in err_str or "Connection error" in err_str:
            return JsonResponse(
                {"error": "OpenAI 서버에 연결할 수 없습니다. 네트워크 상태를 확인해 주세요."},
                status=503,
            )
        # OpenAI 요청 한도 초과
        if "RateLimitError" in err_str or "429" in err_str:
            return JsonResponse(
                {"error": "OpenAI API 요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요."},
                status=429,
            )
        return JsonResponse(
            {"error": f"파이프라인 오류: {err_str}", "quotes": [], "messages": []},
            status=500,
        )
