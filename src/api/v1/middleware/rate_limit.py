import json
import math
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.core.context import current_tenant_ctx
from src.infrastructure.database.redis.connection import get_redis

# Lua script: atomically increment and set TTL on first call.
# Returns current count after increment.
_LUA_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

# Route prefixes and their rate-limit type
_ROUTE_TYPES: list[tuple[str, str]] = [
    ("/v1/chat", "chat"),
    ("/v2/chat", "chat"),
    ("/v1/ingest", "upload"),
]

_DEFAULT_LIMITS = {
    "chat": 60,    # requests per minute
    "upload": 100, # requests per day
}

_TTL_SECONDS = {
    "chat": 60,
    "upload": 86_400,
}

_SKIP_PREFIXES = ("/v1/health", "/docs", "/openapi.json", "/redoc", "/metrics")


def _get_route_type(path: str) -> str | None:
    for prefix, rt in _ROUTE_TYPES:
        if path.startswith(prefix):
            return rt
    return None


def _window_start(route_type: str) -> int:
    ttl = _TTL_SECONDS[route_type]
    return math.floor(time.time() / ttl) * ttl


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            return await call_next(request)

        route_type = _get_route_type(path)
        if route_type is None:
            return await call_next(request)

        tenant = current_tenant_ctx.get()
        if tenant is None:
            # No tenant context yet (public route slipped through) — skip limiting
            return await call_next(request)

        # Determine limit from tenant config
        guardrails = (tenant.config.config if tenant.config else {}).get("guardrails", {})
        limit_key = "chat_rpm" if route_type == "chat" else "upload_rpd"
        limit = guardrails.get(limit_key, _DEFAULT_LIMITS[route_type])
        ttl = _TTL_SECONDS[route_type]
        window = _window_start(route_type)
        redis_key = f"{tenant.id}:ratelimit:{route_type}:{window}"

        try:
            r = get_redis()
            current = await r.eval(_LUA_SCRIPT, 1, redis_key, ttl)  # type: ignore[attr-defined]
            current = int(current)
        except Exception:
            # If Redis is down, fail open (don't block requests)
            return await call_next(request)

        remaining = max(0, limit - current)
        reset_at = window + ttl

        if current > limit:
            retry_after = reset_at - int(time.time())
            body = json.dumps({"detail": "Rate limit exceeded"})
            return Response(
                content=body,
                status_code=429,
                headers={
                    "Content-Type": "application/json",
                    "Retry-After": str(max(retry_after, 1)),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response
