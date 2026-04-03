# TASKS — Production Grade Multi-Tenant RAG Bot

Track execution module-by-module from `IMPLEMENTATION.md`.

## Current Status
- [ ] Module 1 complete (Days 1-5)
- [ ] Module 2 complete (Days 6-13)
- [ ] Module 3 complete (Days 14-20)
- [ ] Module 4 complete (Days 21-24)
- [ ] Module 5 complete (Days 25-27)
- [ ] Module 6 complete (Days 28-32)

## Module 1 — Foundation & Infrastructure (Days 1-5)
- [ ] Day 1: Project skeleton, config, docker-compose, health endpoints
- [ ] Day 2: Postgres models + Alembic initial migration
- [ ] Day 3: Auth (JWT + RBAC) + tenant context middleware
- [ ] Day 4: Redis rate limiter + collections CRUD + v1 router
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

### Day X Notes
- Date:
- Completed:
- Tests run:
- Issues found:
- Fixes/decisions:
- Next day prep:
