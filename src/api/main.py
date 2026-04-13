from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.v1.middleware.rate_limit import RateLimitMiddleware
from src.api.v1.middleware.request_id import RequestIDMiddleware
from src.api.v1.middleware.tenant_context import TenantContextMiddleware
from src.api.v1.router import v1_router
from src.core.config import get_settings
from src.core.exceptions import (
    AuthError,
    CollectionNotFoundError,
    DuplicateResourceError,
    PermissionDeniedError,
    RateLimitExceededError,
    TenantNotFoundError,
    UserNotFoundError,
)
from src.infrastructure.database.postgres.connection import engine
from src.infrastructure.database.redis.connection import close_redis, init_redis
from src.infrastructure.vector_store.qdrant_client import close_qdrant, init_qdrant

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage the application lifecycle:
    - Startup:  initialise DB engine, Redis pool, Qdrant client.
    - Shutdown: close all connections cleanly.
    """
    # ── Startup ──────────────────────────────────────────────────────────────
    app.state.db_engine = engine
    app.state.redis = await init_redis(settings)
    app.state.qdrant = await init_qdrant(settings)

    yield  # application runs here

    # ── Shutdown ─────────────────────────────────────────────────────────────
    await close_redis()
    await close_qdrant()
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="RAG Chatbot API",
        description="Production-grade multi-tenant RAG chatbot",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── Middleware (outermost → innermost) ────────────────────────────────────
    # Order matters: added last = executed first for requests, last for responses.
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception handlers ────────────────────────────────────────────────────
    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers or {},
        )

    @app.exception_handler(PermissionDeniedError)
    async def permission_error_handler(request: Request, exc: PermissionDeniedError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(TenantNotFoundError)
    async def tenant_not_found_handler(request: Request, exc: TenantNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(UserNotFoundError)
    async def user_not_found_handler(request: Request, exc: UserNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(CollectionNotFoundError)
    async def collection_not_found_handler(request: Request, exc: CollectionNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(DuplicateResourceError)
    async def duplicate_resource_handler(request: Request, exc: DuplicateResourceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(request: Request, exc: RateLimitExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers or {},
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(v1_router, prefix="/v1")

    # ── Root landing page ─────────────────────────────────────────────────────
    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def root() -> HTMLResponse:
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>RAG Chatbot API</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: "Segoe UI", system-ui, sans-serif;
      background: #0f1117;
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 2rem;
    }
    .card {
      background: #1a1d27;
      border: 1px solid #2d3148;
      border-radius: 16px;
      max-width: 720px;
      width: 100%;
      padding: 2.5rem;
    }
    .badge {
      display: inline-block;
      background: #2563eb22;
      border: 1px solid #3b82f6;
      color: #60a5fa;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.2rem 0.6rem;
      border-radius: 999px;
      margin-bottom: 1rem;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    h1 { font-size: 1.75rem; font-weight: 700; color: #f8fafc; margin-bottom: 0.4rem; }
    .version { font-size: 0.85rem; color: #64748b; margin-bottom: 1rem; }
    p { color: #94a3b8; line-height: 1.6; margin-bottom: 1.5rem; }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem;
      margin-bottom: 1.75rem;
    }
    @media (max-width: 500px) { .grid { grid-template-columns: 1fr; } }
    .meta-item {
      background: #0f1117;
      border: 1px solid #2d3148;
      border-radius: 10px;
      padding: 0.75rem 1rem;
    }
    .meta-label { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 0.2rem; }
    .meta-value { font-size: 0.9rem; color: #e2e8f0; font-weight: 500; }
    .links { display: flex; flex-wrap: wrap; gap: 0.6rem; }
    a.link-btn {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.5rem 1rem;
      border-radius: 8px;
      font-size: 0.85rem;
      font-weight: 500;
      text-decoration: none;
      transition: opacity 0.15s;
    }
    a.link-btn:hover { opacity: 0.8; }
    .btn-primary  { background: #2563eb; color: #fff; }
    .btn-secondary { background: #1e293b; color: #94a3b8; border: 1px solid #2d3148; }
    .btn-green    { background: #166534; color: #86efac; border: 1px solid #16a34a; }
    .divider { border: none; border-top: 1px solid #2d3148; margin: 1.5rem 0; }
    .stack { display: flex; flex-wrap: wrap; gap: 0.4rem; }
    .tag {
      background: #0f1117;
      border: 1px solid #2d3148;
      color: #94a3b8;
      font-size: 0.75rem;
      padding: 0.2rem 0.55rem;
      border-radius: 6px;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">API</div>
    <h1>RAG Chatbot API</h1>
    <div class="version">v0.1.0 &nbsp;&bull;&nbsp; Production-grade multi-tenant RAG platform</div>
    <p>
      A fully async, multi-tenant retrieval-augmented generation platform with per-client
      dynamic configuration, enterprise observability, and a pluggable ingestion pipeline.
    </p>

    <div class="grid">
      <div class="meta-item">
        <div class="meta-label">Environment</div>
        <div class="meta-value">""" + settings.app_env + """</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">API Prefix</div>
        <div class="meta-value">/v1</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Auth</div>
        <div class="meta-value">JWT &nbsp;(RS256)</div>
      </div>
      <div class="meta-item">
        <div class="meta-label">Multi-Tenancy</div>
        <div class="meta-value">Enabled</div>
      </div>
    </div>

    <hr class="divider" />

    <div class="meta-label" style="margin-bottom:0.6rem">Stack</div>
    <div class="stack" style="margin-bottom:1.5rem">
      <span class="tag">FastAPI</span>
      <span class="tag">PostgreSQL</span>
      <span class="tag">Redis</span>
      <span class="tag">RabbitMQ</span>
      <span class="tag">Celery</span>
      <span class="tag">Qdrant</span>
      <span class="tag">LangSmith</span>
      <span class="tag">Prometheus</span>
      <span class="tag">AWS S3</span>
    </div>

    <div class="links">
      <a class="link-btn btn-primary" href="/docs">Swagger UI</a>
      <a class="link-btn btn-secondary" href="/redoc">ReDoc</a>
      <a class="link-btn btn-secondary" href="/openapi.json">OpenAPI JSON</a>
      <a class="link-btn btn-green" href="/v1/health">Health Check</a>
    </div>
  </div>
</body>
</html>"""
        return HTMLResponse(content=html)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
