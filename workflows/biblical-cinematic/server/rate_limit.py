"""
Shared rate limiter for the unified web app.

Used by app.py, biblical_pipeline.py, and custom-script/router.py so all three
share one limit counter per IP.

Tiers:
  5/hour  — endpoints that spend real money (FLUX + Kling + JSON2Video renders)
  30/hour — endpoints that call Claude only (scene generation, text cleaning)

IP resolution: reads X-Forwarded-For first since Modal sits behind a proxy;
falls back to request.client.host for local dev.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip)

EXPENSIVE_LIMIT = "5/hour"
MEDIUM_LIMIT = "30/hour"


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": f"Rate limit exceeded ({exc.detail}). Try again later.",
            "limit": str(exc.detail),
        },
    )
