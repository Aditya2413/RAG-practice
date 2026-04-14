# TASKS — Production Grade Multi-Tenant RAG Bot

Track execution module-by-module from `IMPLEMENTATION.md`.

## Current Status
- [ ] Module 1 complete (Days 1-5)
- [ ] Module 2 complete (Days 6-13)
- [ ] Module 3 complete (Days 14-20)
- [ ] Module 4 complete (Days 21-24)
- [ ] Module 5 complete (Days 25-27)
- [ ] Module 6 complete (Days 28-32)

> Days 1–4 implementation files are fully written. Day 5 (S3 + Qdrant + Celery) is next.

## Module 1 — Foundation & Infrastructure (Days 1-5)
- [x] Day 1: Project skeleton, config, docker-compose, health endpoints
- [x] Day 2: Postgres models + Alembic initial migration
- [x] Day 3: Auth (JWT + RBAC) + tenant context middleware
- [x] Day 4: Redis rate limiter + collections CRUD + v1 router
- [ ] Day 5: S3 storage layer + Qdrant client/store + Celery app bootstrap

## Module 2 — Ingestion Pipeline (Days 6-13)
- [ ] Day 6: Ingestion upload API + ingestion job tracking endpoints
- [ ] Day 7: Parser base + PDF digital parser
- [ ] Day 8: OCR parser for scanned/mixed PDFs
- [ ] Day 9: Image parser + image extraction path for PDFs
- [ ] Day 10: CSV + Excel parsers
- [ ] Day 11: Audio + video parsers
- [ ] Day 12: Parser factory + chunkers + enrichers
- [ ] Day 13: Celery ingestion worker end-to-end flow

## Module 3 — RAG Query Pipeline (Days 14-20)
- [ ] Day 14: Embedding service + dense retrieval
- [ ] Day 15: Sparse retrieval + ensemble RRF retrieval
- [ ] Day 16: Query rewriting + reranking
- [ ] Day 17: LLM service + prompt manager + response cache
- [ ] Day 18: Session management + memory (STM/LTM)
- [ ] Day 19: Retrieval orchestration service
- [ ] Day 20: Guardrails service (input/output)

## Module 4 — Chat Service + Streaming (Days 21-24)
- [ ] Day 21: Chat service orchestration (full RAG + memory + guardrails)
- [ ] Day 22: REST chat API + WebSocket chat endpoint
- [ ] Day 23: v2 SSE streaming + final router wiring
- [ ] Day 24: End-to-end integration tests

## Module 5 — Observability (Days 25-27)
- [ ] Day 25: Prometheus metrics instrumentation
- [ ] Day 26: Grafana dashboards + alerting baseline
- [ ] Day 27: Structured logging + tracing + LangSmith integration

## Module 6 — Production Hardening (Days 28-32)
- [ ] Day 28: Nginx reverse proxy + security headers + TLS readiness
- [ ] Day 29: Docker multi-stage builds + prod compose
- [ ] Day 30: Pre-commit + CI pipeline
- [ ] Day 31: Cleanup worker + webhooks
- [ ] Day 32: Final integration + load test + handoff checklist

## Definition of Done (Per Day)
- [ ] Feature implemented in target files
- [ ] Unit/integration tests added or updated
- [ ] Local verification commands run successfully
- [ ] Notes updated in this file (what changed, blockers, next step)

## Daily Notes Template
Copy this section for each day while executing:

### Day 1 Notes
- Date: 2026-04-12
- Completed: config.py, main.py, health router, postgres/redis/qdrant connections, docker-compose, Makefile
- Tests run: curl /health/ready
- Issues found: None
- Fixes/decisions: —
- Next day prep: docker-compose up before running migrations

### Day 2 Notes
- Date: 2026-04-13
- Completed: models/base.py (Base + TimestampMixin), all 8 model files + RefreshToken, alembic.ini, migrations/env.py (async), versions/001_initial_schema.py (9 tables + all indexes), scripts/migrate.sh
- Tests run: `python -m alembic upgrade head` — code parses correctly; DB connection failed because Docker was not running
- Issues found: Docker Desktop was not started at verification time
- Fixes/decisions: Run `make dev` first, then `make migrate` to apply
- Next day prep: Day 3 — Auth system (JWT + RBAC). Needs docker running + `make migrate` verified.

### Day 3 Notes
- Date: 2026-04-14
- Completed: security.py (JWT RS256/HS256, bcrypt, refresh token rotation), auth router (register/login/refresh/logout/me), all 4 middlewares (RequestID, TenantContext, RateLimit, auth helper), dependencies.py (get_current_user + require_role RBAC, current_user_ctx now set), core/constants.py (role constants + pagination defaults), repositories (user, tenant, collection), tenant_service, collections router, all schemas. tests/conftest.py (async fixtures: db_session, async_client, tenant_factory, user_factory). tests/integration/test_auth_flow.py (13 tests covering register/login/me/refresh/logout happy + error paths).
- Note: Day 4 (rate limiter + collections CRUD + v1 router) was already fully implemented alongside Day 3 scaffolding — marked complete.
- Gap fixed: get_current_user now calls current_user_ctx.set(user) so service layer has access without param threading.
- Tests run: `pytest tests/integration/test_auth_flow.py -v` (requires `make dev` + `make migrate` first)
- Issues found: None
- Fixes/decisions: Used SAVEPOINT-based rollback in conftest for test isolation; test DB = ragbot_test (auto-created)
- Next day prep: Day 5 — S3 storage layer + Qdrant client/store + Celery app bootstrap
