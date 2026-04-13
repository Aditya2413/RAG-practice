# Production-Grade Multi-Tenant RAG Chatbot

## Project Overview

A production-ready RAG (Retrieval-Augmented Generation) chatbot platform with full multi-tenancy, dynamic per-client configuration, and enterprise observability. Every aspect of the pipeline (LLM, retrieval, guardrails, memory) is configurable per tenant at runtime.

**Stack:** FastAPI · PostgreSQL · Redis · RabbitMQ · Celery · Qdrant · LangSmith · Prometheus · Grafana · AWS S3

**Target:** 32 implementation days (~6–8 weeks). See `IMPLEMENTATION.md` for the full day-by-day plan.

---

## Architecture

```
Client → NGINX → FastAPI
                 Middleware: RequestID → TenantContext → RateLimiter → Auth → Router
                 API v1: /auth /ingest /chat /ws/chat /tenants /collections /sessions /documents /health /metrics
                 API v2: /chat/stream (SSE) /agents

FastAPI ──► PostgreSQL  (relational, source of truth)
        ──► Redis       (STM cache, rate limiting, response cache)
        ──► RabbitMQ    (task queue) → Celery Workers → S3 + Qdrant

LangSmith ← all LLM calls traced
Prometheus ← /metrics scraped every 15s
Grafana   ← dashboards + alerting
```

---

## Directory Layout

```
src/
├── api/
│   ├── main.py                  # FastAPI app factory with lifespan
│   ├── dependencies.py          # get_current_user, require_role(), get_db
│   ├── v1/
│   │   ├── routers/             # auth, tenants, collections, ingestion, documents, sessions, chat, websocket, health
│   │   ├── schemas/             # Pydantic request/response models
│   │   └── middleware/          # auth_middleware, rate_limit, request_id, tenant_context
│   └── v2/routers/chat.py       # SSE streaming
├── core/
│   ├── config.py                # Pydantic BaseSettings, @lru_cache
│   ├── security.py              # JWT (RS256), bcrypt
│   ├── exceptions.py            # AuthError, PermissionError, TenantNotFoundError, etc.
│   └── logging.py               # structlog JSON config
├── domain/
│   ├── entities/                # tenant, user, document, session, job
│   └── value_objects/           # tenant_id, embedding, chunk (ParsedPage, DocumentChunk, RetrievedChunk)
├── services/
│   ├── ingestion/               # ingestion_service + parsers + chunkers + enrichers
│   ├── embedding/               # embedding_service + providers (openai, cohere)
│   ├── retrieval/               # retrieval_service + retrievers + rerankers + filters
│   ├── llm/                     # llm_service + prompt_manager + response_cache + providers
│   ├── memory/                  # short_term (Redis STM) + long_term (Qdrant LTM)
│   ├── guardrails/              # input (PII, toxicity, injection, topic) + output (hallucination, citations)
│   ├── chat/chat_service.py     # main RAG orchestrator
│   ├── session/session_service.py
│   └── tenant/tenant_service.py
├── infrastructure/
│   ├── database/postgres/       # connection, models (8 tables), migrations (Alembic)
│   ├── database/redis/          # aioredis connection pool
│   ├── repositories/            # base + one per entity (tenant, user, collection, document, job, session, message)
│   ├── vector_store/            # qdrant_client (singleton), qdrant_store (CRUD)
│   ├── storage/s3_storage.py    # aioboto3, presigned URLs
│   ├── message_queue/           # celery_app (queue routing), rabbitmq_publisher
│   └── observability/           # langsmith_client, prometheus_metrics, tracing
└── workers/
    ├── ingestion_worker.py      # full 8-step Celery pipeline
    ├── ltm_worker.py            # async LTM summarization (every 20 turns)
    └── cleanup_worker.py        # expired jobs/sessions/S3 orphans
```

---

## Multi-Tenancy & Isolation

| Layer | Isolation Mechanism |
|---|---|
| API | JWT payload contains `tenant_id`; TenantContextMiddleware injects into Python `ContextVar` |
| PostgreSQL | Every table has `tenant_id`; all queries filter by it |
| Qdrant | Separate collection per tenant: `tenant_{tenant_id}` + `ltm_{tenant_id}` |
| Redis | All keys namespaced: `{tenant_id}:{key_type}:{id}` |
| S3 | All objects under `s3://bucket/{tenant_id}/` |
| Celery | Tasks carry `tenant_id`; workers validate before processing |

**Roles:** `SUPER_ADMIN` > `CLIENT_ADMIN` > `CLIENT_USER`

---

## Database Schema (PostgreSQL)

8 tables: `tenants`, `tenant_configs` (JSONB config blob), `users`, `collections`, `documents`, `ingestion_jobs`, `sessions`, `messages`

- All secrets/config in `tenant_configs.config` (JSONB) — no hardcoded pipeline values
- `sessions.config_snapshot` = copy of tenant config at session creation (mid-session changes don't break UX)
- Soft-delete on `documents` (deleted_at column)
- SHA256 deduplication: `UNIQUE(tenant_id, sha256)` on documents

**Qdrant Collections:**
- `tenant_{id}`: vectors size=1536 (text-embedding-3-large), Cosine, sparse BM25 for hybrid search
- `ltm_{id}`: user long-term memory summaries, filtered by `user_id`

---

## Ingestion Pipeline (Celery Worker)

File upload → S3 → RabbitMQ → Celery worker:

1. DOWNLOADING (S3 → /tmp)
2. CLASSIFYING (PDF: digital/scanned/blank per page)
3. PARSING (ParserFactory by MIME type)
4. CHUNKING (ChunkerFactory by content_type)
5. ENRICHING (metadata + YAKE keywords)
6. EMBEDDING (batched, 100/request, per-tenant model)
7. INDEXING (Qdrant upsert, 500 points/batch)
8. CLEANUP (/tmp removed in finally block)

**Parser routing:** PDF → pdfplumber/Tesseract OCR | images → GPT-4o vision | CSV/Excel → verbalized rows | audio → Whisper | video → ffmpeg + Whisper + keyframe captions

**Error handling:** Transient errors → retry (exponential backoff, max 3). Permanent errors → FAILED + DLQ + webhook.

**Celery task config:** `acks_late=True`, `reject_on_worker_lost=True`

---

## Chat Query Pipeline (ChatService)

1. Input guardrails — `asyncio.gather()` (PII mask/reject, toxicity, prompt injection, topic classifier)
2. STM + LTM load — parallel (Redis lpush window, Qdrant ltm search)
3. Query rewriting — MultiQuery (3 variants) + HyDE (hypothetical doc embedding)
4. Ensemble retrieval — Dense (Qdrant ANN) + Sparse (BM25) → RRF merge
5. Reranking — Cohere cross-encoder → top_k
6. Cache check — `sha256(tenant_id + normalized_message)` in Redis
7. Prompt construction — system (LangSmith Hub) + STM history + LTM facts + RAG context
8. LLM call — stream (WS/SSE) or full (REST), traced in LangSmith
9. Output guardrails — PII scrub, hallucination NLI check, citation validation
10. Cache write + STM update + LTM enqueue (every 20 turns)
11. Persist message to PostgreSQL

**Token budget:** trim oldest STM turns first if over context limit. Never trim RAG context or system prompt.

---

## API Endpoints

```
POST   /v1/auth/login|refresh|logout
GET    /v1/auth/me
GET|POST|PATCH|DELETE  /v1/tenants/{id}
GET|PUT|PATCH          /v1/tenants/{id}/config
GET|POST|PATCH|DELETE  /v1/collections/{id}
POST   /v1/ingest/upload        → {job_id, document_id, status: "QUEUED"}
GET    /v1/ingest/status/{job_id}
GET    /v1/documents
DELETE /v1/documents/{id}       → Qdrant → S3 → soft-delete PG (in that order)
POST   /v1/sessions
DELETE /v1/sessions/{id}
GET    /v1/sessions/{id}/history
POST   /v1/chat/completions     # REST full response
WS     /v1/ws/chat/{session_id} # WebSocket streaming (JWT via ?token= query param)
GET    /v2/chat/stream          # SSE streaming
GET    /health/ready            # checks PG, Redis, Qdrant
GET    /metrics                 # Prometheus scrape
```

---

## Key Implementation Conventions

- **Config:** All values from env vars via `pydantic-settings`. `@lru_cache` on settings. No hardcoded secrets or pipeline params.
- **JWT:** RS256 asymmetric. Payload: `{sub: user_id, tenant_id, role, exp}`. Refresh tokens stored hashed in DB with rotation.
- **Auth in DI, not middleware:** `require_role(*roles)` is a FastAPI dependency, not middleware — allows per-route flexibility.
- **Middleware order** (outermost → innermost): CORS → RequestID → TenantContext → RateLimit. Auth is a dependency.
- **Rate limiting:** Lua script atomic `INCR + EXPIRE` in Redis. Two types: per-minute (chat), per-day (uploads). Returns `X-RateLimit-*` headers.
- **Async throughout:** All services are `async def`. DB via asyncpg, Redis via aioredis, S3 via aioboto3.
- **ContextVar propagation:** `tenant_id`, `user_id`, `request_id`, `session_id` bound to `ContextVar` at middleware — no param threading through service layer.
- **Parser ABCs:** `IDocumentParser.parse()` is async (VLM calls inside are awaitable).
- **Whisper:** Load model once as class-level singleton. Never load inside `parse()`.
- **Embedding batching:** 100 texts/request, Tenacity retry on `RateLimitError`.
- **Qdrant upsert:** 500 points/batch (recommended size).
- **Response cache normalization:** lowercase + remove punctuation + sort words for near-duplicate detection.
- **PromptManager:** Cache LangSmith Hub prompts 10 min in memory. Version-pinned (`"stable"`).
- **Structlog:** Every log line includes `request_id`, `tenant_id`, `user_id`, `session_id`. No JWT/passwords logged.

---

## Environment Variables

See `.env.example`. Key vars:
- `APP_SECRET_KEY` / `APP_PUBLIC_KEY` — RS256 PEM keys
- `POSTGRES_*`, `REDIS_*`, `RABBITMQ_*`, `CELERY_BROKER_URL`
- `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_API_KEY`
- `AWS_*`, `S3_BUCKET_NAME`
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `COHERE_API_KEY`
- `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`

---

## Development Workflow

```bash
make dev        # docker-compose up (postgres, redis, rabbitmq, qdrant, adminer)
make migrate    # alembic upgrade head
make worker     # celery -A src.infrastructure.message_queue.celery_app worker
make test       # pytest
make lint       # ruff + mypy
```

Infra UIs: RabbitMQ `localhost:15672`, Adminer `localhost:8080`, Qdrant `localhost:6333/dashboard`, Grafana `localhost:3000`

---

## Testing Strategy

- **Unit tests** (`tests/unit/`): pure logic, no I/O, mock all external calls with `AsyncMock`
- **Integration tests** (`tests/integration/`): real Postgres/Redis/Qdrant via testcontainers; mock OpenAI/Cohere/S3 (LocalStack). `task_always_eager=True` for Celery.
- **E2E tests**: full docker-compose stack, upload → index → query flow
- **LangSmith eval** (CI gate): 50 QA pairs in `tests/golden_datasets/qa_pairs_sample.jsonl`, recall@5 must be ≥ 0.85
- **CI:** ruff + mypy → unit tests → integration tests → bandit security scan → LangSmith eval

---

## Module Build Order (Dependencies)

```
Day 1-5:   Foundation (infra skeleton → DB → auth → Redis/rate-limit → S3/Qdrant/Celery)
Day 6-13:  Ingestion pipeline (API → parsers → chunkers → worker)
Day 14-20: RAG query pipeline (dense/sparse retrieval → reranking → LLM → memory → guardrails)
Day 21-24: Chat API + WebSocket + SSE + integration tests
Day 25-27: Observability (Prometheus + Grafana + structured logging)
Day 28-32: Production hardening (Nginx + Docker + CI + cleanup worker + load test)
```
