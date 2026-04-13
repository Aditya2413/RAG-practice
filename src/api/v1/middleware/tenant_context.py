import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from src.api.v1.middleware.auth_middleware import extract_token_from_header
from src.core.context import current_tenant_ctx
from src.core.exceptions import AuthError, TenantNotFoundError
from src.core.security import decode_access_token
from src.infrastructure.database.postgres.connection import AsyncSessionLocal
from src.infrastructure.repositories.tenant_repository import TenantRepository

# Routes that do NOT require authentication/tenant loading
_PUBLIC_PREFIXES = (
    "/v1/health",
    "/v1/auth/login",
    "/v1/auth/refresh",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/metrics",
)


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
            return await call_next(request)

        token = extract_token_from_header(request)
        if token is None:
            return _json_error(401, "Authentication required", {"WWW-Authenticate": "Bearer"})

        try:
            payload = decode_access_token(token)
        except AuthError as exc:
            return _json_error(401, exc.detail, {"WWW-Authenticate": "Bearer"})

        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            return _json_error(401, "Token missing tenant_id")

        async with AsyncSessionLocal() as session:
            repo = TenantRepository(session)
            tenant = await repo.find_by_id(tenant_id)

        if tenant is None:
            return _json_error(404, "Tenant not found")

        ctx_token = current_tenant_ctx.set(tenant)
        try:
            response = await call_next(request)
        finally:
            current_tenant_ctx.reset(ctx_token)

        return response


def _json_error(status_code: int, detail: str, headers: dict | None = None) -> Response:
    body = json.dumps({"detail": detail})
    return Response(
        content=body,
        status_code=status_code,
        headers={**(headers or {}), "Content-Type": "application/json"},
    )
