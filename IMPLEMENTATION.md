# Production-Grade Multi-Tenant RAG Chatbot — Implementation Plan

> **Working principle:** One module per day. Each day has a clear deliverable you can run and verify.  
> **Stack:** FastAPI · PostgreSQL · Redis · RabbitMQ · Celery · Qdrant · LangSmith · Prometheus · Grafana · AWS S3

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Complete System Flows](#2-complete-system-flows)
3. [Multi-Tenant & Session Design](#3-multi-tenant--session-design)
4. [Dynamic Per-Client Configuration](#4-dynamic-per-client-configuration)
5. [Database Schema](#5-database-schema)
6. [API Contract](#6-api-contract)
7. [Project Directory Tree](#7-project-directory-tree)
8. [Daily Implementation Plan](#8-daily-implementation-plan)
9. [Environment Variables Reference](#9-environment-variables-reference)
10. [Testing Strategy](#10-testing-strategy)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                              │
│         Browser / Mobile App / Third-Party Integration           │
└──────────────────────┬──────────────────────────────────────────┘
                       │  HTTPS / WSS
┌──────────────────────▼──────────────────────────────────────────┐
│                    NGINX (Reverse Proxy)                          │
│          TLS termination · WebSocket upgrade · gzip              │
└──────────────────────┬──────────────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│                  FastAPI Application                              │
│                                                                   │
│  Middleware Stack (in order):                                     │
│  RequestID → TenantContext → RateLimiter → Auth → Router         │
│                                                                   │
│  ┌─── API v1 ────────────────────────────────────────────────┐  │
│  │  /auth  /ingest  /chat  /ws/chat  /tenants  /collections  │  │
│  │  /sessions  /documents  /health  /metrics                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌─── API v2 ─────────────────────────────────────────────────┐  │
│  │  /chat/stream (SSE)  /agents                               │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────┬────────────┬────────────────┬────────────────────────────┘
       │            │                │
       ▼            ▼                ▼
  PostgreSQL      Redis           RabbitMQ
  (relational)   (cache/STM/     (task queue)
                  rate-limit)         │
                                      ▼
                              Celery Workers
                              (ingestion tasks)
                                      │
                              ┌───────┴────────┐
                              │                │
                             S3            Qdrant
                          (raw files)   (vectors per tenant)

  LangSmith ←── all LLM calls traced
  Prometheus ←── /metrics scraped every 15s
  Grafana ←── dashboards + alerting
```

---

## 2. Complete System Flows

### 2.1 File Ingestion Flow (Full Detail)

```
STEP 1 — CLIENT UPLOADS FILE
  POST /v1/ingest/upload
  Headers: Authorization: Bearer <JWT>
  Body: multipart/form-data
    - file: <binary>
    - collection_id: "legal-docs-2024"
    - metadata: {"department": "legal", "year": "2024"}

STEP 2 — MIDDLEWARE PIPELINE
  a. RequestID:      generate UUID4 → X-Request-ID header
  b. TenantContext:  decode JWT → extract {tenant_id, user_id, role}
                     → inject into Python ContextVar (no param threading)
  c. RateLimiter:    Redis INCR ingestion:{tenant_id}:daily
                     if count > tenant.upload_quota_per_day → 429
  d. Auth:           validate JWT signature + expiry
                     check role in [CLIENT_ADMIN, SUPER_ADMIN] → else 403

STEP 3 — INGESTION ROUTER (validation only)
  a. python-magic MIME detection on file bytes (not extension)
  b. File size check: file.size <= tenant.max_file_size_mb * 1024 * 1024
  c. MIME type allowed: mime in tenant.allowed_mime_types
  d. SHA256 deduplication:
       hash = sha256(file.read())
       existing = SELECT id FROM documents WHERE tenant_id=X AND sha256=hash
       if existing → return 409 {document_id: existing.id, message: "already indexed"}

STEP 4 — INGESTION SERVICE
  a. Generate document_id (UUID4)
  b. Upload to S3: s3://{BUCKET}/{tenant_id}/{document_id}/{original_filename}
  c. INSERT ingestion_jobs (job_id, document_id, tenant_id, status=PENDING, ...)
  d. INSERT documents (document_id, tenant_id, collection_id, sha256, s3_key, ...)
  e. Publish to RabbitMQ — message is SMALL (no file bytes):
     {
       "job_id": "...",
       "document_id": "...",
       "tenant_id": "...",
       "collection_id": "...",
       "s3_key": "s3://bucket/tenant/doc/file.pdf",
       "mime_type": "application/pdf",
       "original_filename": "contract.pdf",
       "sha256": "abc123...",
       "upload_metadata": {"department": "legal"}
     }
  f. Return immediately: {job_id, document_id, status: "QUEUED"}

STEP 5 — RABBITMQ ROUTING
  Exchange: rag.ingestion (direct)
  Routing key logic based on mime_type:
    application/pdf, image/tiff          → queue: ingestion.documents
    image/jpeg, image/png, image/webp    → queue: ingestion.images
    application/vnd.ms-excel,
    application/vnd.openxmlformats...,
    text/csv                             → queue: ingestion.tabular
    audio/*                              → queue: ingestion.media
    video/*                              → queue: ingestion.media
    */*  (unknown)                       → queue: ingestion.documents

STEP 6 — CELERY WORKER (acks_late=True, reject_on_worker_lost=True)

  6.1 UPDATE job status → DOWNLOADING
      Download file from S3 → /tmp/{job_id}/{filename}

  6.2 UPDATE job status → CLASSIFYING
      PDF-specific: classify_pdf(path) → per-page {type: digital|scanned|blank}
      Other types: mime_type already known

  6.3 UPDATE job status → PARSING
      parser = ParserFactory.get_parser(mime_type, pdf_classification)
      parsed_pages = await parser.parse(file_path, document_id, tenant_id)
      # Each ParsedPage: {text, tables[], images[], page_num, content_type}
      # Filter: skip pages where len(text.strip()) < 50 AND no images

  6.4 UPDATE job status → CHUNKING
      chunker = ChunkerFactory.get_chunker(content_type)
      chunks = chunker.chunk(parsed_pages)
      # Digital PDF/text → RecursiveCharacter (512 tokens, 64 overlap)
      # Tables          → TableChunker (header in every chunk)
      # CSV rows        → verbalized sentence per row
      # Transcripts     → 200-word grouped segments

  6.5 UPDATE job status → ENRICHING
      for chunk in chunks:
        chunk.metadata.update({
          "tenant_id": tenant_id,
          "document_id": document_id,
          "collection_id": collection_id,
          "chunk_index": i,
          "source_filename": original_filename,
          "doc_type": content_type,
          "sha256": sha256,
          "created_at": utcnow(),
          "quality": "high" if ocr_conf > 70 else "low",
          **upload_metadata   # department, year, etc from user
        })
        keywords = yake_extractor.extract(chunk.text, top_n=10)
        chunk.metadata["keywords"] = keywords

  6.6 UPDATE job status → EMBEDDING
      vectors = await embedding_service.embed_batch(
          texts=[c.text for c in chunks],
          model=tenant.embedding_model,   # per-tenant config
          batch_size=100
      )

  6.7 UPDATE job status → INDEXING
      qdrant_store.upsert(
          collection_name=f"tenant_{tenant_id}",
          points=[{
              "id": str(uuid4()),
              "vector": vectors[i],
              "payload": chunks[i].metadata | {"text": chunks[i].text}
          } for i in range(len(chunks))]
      )
      UPDATE documents SET chunk_count=len(chunks), status=INDEXED
      UPDATE job status → COMPLETED, completed_at=utcnow()

  6.8 CLEANUP
      rm -rf /tmp/{job_id}/

  ON ANY ERROR:
      If retryable (network, API timeout):
          raise self.retry(countdown=2 ** attempt * 60, max_retries=3)
      If permanent (corrupt file, unsupported encoding):
          UPDATE job status → FAILED, error_message=str(e)
          Route to DLQ: ingestion.dlq
          Send webhook notification if tenant.webhook_url configured

CLIENT POLLS: GET /v1/ingest/status/{job_id}
  → {status, progress_pct, chunk_count, error_message, completed_at}
```

---

### 2.2 Chat Query Flow (Full Detail)

```
STEP 1 — CLIENT SENDS QUERY
  Option A: POST /v1/chat/completions  (REST, full response)
  Option B: WebSocket /v1/ws/chat/{session_id}  (streaming, real-time)
  Option C: GET /v2/chat/stream  (SSE, streaming for REST clients)

  Payload:
  {
    "message": "What are the indemnification clauses in Q3 contracts?",
    "session_id": "sess_abc123",       ← null = create new session
    "collection_ids": ["legal-docs"],  ← null = search all tenant collections
    "filters": {"year": "2024"}        ← optional metadata pre-filter
  }

STEP 2 — MIDDLEWARE (same as ingestion, tenant context injected)

STEP 3 — SESSION RESOLUTION
  if session_id is null:
      session_id = create_session(user_id, tenant_id)
      → INSERT sessions (session_id, user_id, tenant_id, created_at, config_snapshot)
      config_snapshot = tenant.chat_config  ← snapshot at session creation
                                              so mid-session config changes don't break UX
  else:
      session = get_session(session_id)
      validate session.tenant_id == request.tenant_id  ← cross-tenant isolation
      validate session.user_id == request.user_id

STEP 4 — LOAD DYNAMIC CLIENT CONFIG
  config = tenant_config_service.get(tenant_id)
  # Config drives EVERYTHING below:
  {
    "llm_provider": "openai",
    "llm_model": "gpt-4o",
    "temperature": 0.2,
    "max_tokens": 1024,
    "system_prompt_id": "legal-assistant-v3",   ← LangSmith Hub ID
    "top_k": 5,
    "similarity_threshold": 0.72,
    "reranker_enabled": true,
    "reranker_model": "cohere",
    "hybrid_alpha": 0.7,          ← 0=sparse only, 1=dense only
    "guardrails": {
      "pii_detection": true,
      "toxicity_filter": true,
      "hallucination_check": true,
      "topic_restriction": ["legal", "contracts", "compliance"],
      "pii_action": "mask"         ← mask | reject | allow
    },
    "stm_window": 10,              ← last N turns kept in Redis
    "ltm_enabled": true,
    "response_cache_ttl": 3600,
    "streaming": true
  }

STEP 5 — INPUT GUARDRAILS (run in parallel)
  Task A: PIIDetector.scan(message)
    → if PII found:
        if config.guardrails.pii_action == "mask"   → replace with [PII_MASKED]
        if config.guardrails.pii_action == "reject"  → return 422 immediately
  Task B: ToxicityFilter.check(message)
    → if flagged → return 422 {reason: "content_policy_violation"}
  Task C: PromptInjectionDetector.check(message)
    → if injection detected → return 422 {reason: "prompt_injection_detected"}
  Task D: TopicClassifier.check(message, allowed_topics=config.topic_restriction)
    → if off_topic → return 422 {reason: "off_topic", allowed: config.topic_restriction}

  All 4 run as asyncio.gather() — total latency = max(A,B,C,D), not sum

STEP 6 — MEMORY RETRIEVAL (run in parallel)
  Task A: STM (Short-Term Memory) — Redis
    key = stm:{session_id}
    history = redis.lrange(key, 0, config.stm_window - 1)
    → last N turns as [{role, content, timestamp}]
    → used for: conversation context window

  Task B: LTM (Long-Term Memory) — Qdrant
    collection = f"ltm_{tenant_id}"
    results = qdrant.search(
        query_vector=embed(message),
        filter={"user_id": user_id},
        limit=3
    )
    → past conversation summaries, user preferences, stated facts
    → Example: "User prefers bullet-point answers", "User is a paralegal"

STEP 7 — QUERY REWRITING
  a. MultiQuery: LLM generates 3 query variants
     Prompt (from LangSmith Hub, client-specific):
     "Generate 3 different search queries for: {message}"
     → ["indemnification clauses Q3", "liability terms third quarter contracts",
        "Q3 2024 indemnity provisions"]

  b. HyDE (Hypothetical Document Embedding):
     LLM generates hypothetical answer → embed that instead of raw query
     → better semantic match to how answers are phrased in documents

STEP 8 — ENSEMBLE RETRIEVAL
  For each query variant (original + 3 rewrites):
    A. DenseRetriever:
       qdrant.search(
           collection=f"tenant_{tenant_id}",
           query_vector=embed(query_variant),
           query_filter=Filter(
               must=[
                   FieldCondition(key="tenant_id", match=MatchValue(tenant_id)),
                   FieldCondition(key="collection_id", match=MatchAny(collection_ids)),
                   *[FieldCondition(key=k, match=MatchValue(v))
                     for k,v in request.filters.items()]
               ]
           ),
           limit=20
       )
    B. SparseRetriever: BM25 over same Qdrant collection (sparse vectors)
       → returns top 20 by keyword overlap

    C. EnsembleRetriever (RRF — Reciprocal Rank Fusion):
       for each doc: score = Σ 1/(rank_i + 60) across all query variants and retriever types
       take top 20 by RRF score

STEP 9 — RERANKING (if config.reranker_enabled)
  cohere.rerank(
      query=original_message,
      documents=[c.text for c in top_20_chunks],
      model="rerank-english-v3.0",
      top_n=config.top_k   ← e.g. 5
  )
  → final_chunks: top 5 by cross-encoder relevance score

STEP 10 — CACHE CHECK
  cache_key = sha256(f"{tenant_id}:{normalize(message)}")
  cached = redis.get(f"llmcache:{cache_key}")
  if cached:
      → return cached response (skip steps 11-12)
      → log cache hit in Prometheus

STEP 11 — PROMPT CONSTRUCTION
  system_prompt = prompt_manager.load(
      prompt_id=config.system_prompt_id,   ← e.g. "legal-assistant-v3"
      version="stable"                      ← pinned in LangSmith Hub
  )
  # System prompt is fully dynamic per tenant — loaded from LangSmith Hub
  # Example: "You are a legal assistant for {tenant.company_name}. Answer only
  #           based on the provided context. Always cite clause numbers..."

  messages = [
      {"role": "system", "content": system_prompt.format(**tenant.prompt_vars)},
      *stm_history[-config.stm_window:],       ← conversation context
      *ltm_context_as_messages,                ← long-term user facts
      {"role": "user", "content": build_rag_prompt(message, final_chunks)}
  ]
  # Token budget: count tokens, truncate oldest STM history first if over limit

  rag_user_prompt = f"""Context:
{format_chunks_with_citations(final_chunks)}

User question: {message}

Answer based only on the context above. Cite sources as [1], [2], etc."""

STEP 12 — LLM CALL (with LangSmith tracing)
  with langsmith.trace("rag_query", inputs={message, chunks, config}):
      if config.streaming:
          stream = await llm_provider.stream(
              messages=messages,
              model=config.llm_model,
              temperature=config.temperature,
              max_tokens=config.max_tokens
          )
          for chunk in stream:
              await websocket.send_text(chunk)   ← stream token by token
      else:
          response = await llm_provider.generate(messages, ...)

STEP 13 — OUTPUT GUARDRAILS
  a. PIIScrubber: scan LLM output → redact any leaked PII
  b. HallucinationCheck:
       faithfulness_score = nli_model.score(response, context=final_chunks)
       if faithfulness_score < 0.5:
           append disclaimer: "⚠ This answer may not be fully supported by available documents."
  c. CitationValidator:
       validate [1],[2] references exist in final_chunks
       strip invalid citation numbers

STEP 14 — CACHE WRITE + MEMORY UPDATE
  redis.setex(f"llmcache:{cache_key}", config.response_cache_ttl, response)

  # Update STM
  redis.lpush(f"stm:{session_id}", json({role:"user", content:message, ts:now}))
  redis.lpush(f"stm:{session_id}", json({role:"assistant", content:response, ts:now}))
  redis.ltrim(f"stm:{session_id}", 0, config.stm_window * 2 - 1)
  redis.expire(f"stm:{session_id}", 86400 * 7)   ← 7-day TTL

  # Async LTM: if session turn count > 20, enqueue summarization task
  if session.turn_count % 20 == 0:
      celery_app.send_task("workers.ltm_worker.summarize_session",
                           args=[session_id, tenant_id, user_id])

STEP 15 — RESPONSE
  {
    "session_id": "sess_abc123",
    "message_id": "msg_xyz",
    "content": "The indemnification clauses in Q3 contracts...",
    "sources": [
      {"document_id": "...", "filename": "contract_q3.pdf",
       "page": 14, "chunk_text": "...", "relevance_score": 0.94}
    ],
    "usage": {"prompt_tokens": 1240, "completion_tokens": 380},
    "cached": false,
    "session_turn": 3
  }

  Prometheus metrics recorded:
  - rag_query_duration_seconds (histogram)
  - rag_retrieval_chunks_returned (gauge)
  - rag_llm_tokens_total{provider, model, tenant_id} (counter)
  - rag_cache_hits_total{tenant_id} (counter)
  - rag_guardrail_blocks_total{type, tenant_id} (counter)
```

---

### 2.3 Session Lifecycle

```
CREATE SESSION
  POST /v1/sessions
  → session_id = UUID4
  → snapshot tenant config at creation time (so config changes mid-session don't break)
  → Redis STM key initialized (empty)
  → PostgreSQL sessions row inserted

ACTIVE SESSION
  Each chat turn:
  → STM updated in Redis (lpush + ltrim)
  → turn_count incremented in PostgreSQL
  → last_active_at updated

SESSION EXPIRY
  Redis STM TTL = 7 days (sliding — reset on each message)
  PostgreSQL session status = ACTIVE until explicitly ended or 30-day inactivity

LTM SUMMARIZATION (async, every 20 turns)
  Celery ltm_worker:
  → Read last 20 STM turns
  → LLM prompt: "Summarize this conversation. Extract: user preferences,
                  key facts stated, topics discussed, tone preferences."
  → Store summary vector in Qdrant collection: ltm_{tenant_id}
  → Payload: {user_id, session_id, summary_text, created_at, turn_range}

END SESSION
  DELETE /v1/sessions/{session_id}
  → Redis STM key deleted
  → PostgreSQL status = ENDED, ended_at = now()
  → Final LTM summarization triggered

SESSION HISTORY
  GET /v1/sessions/{session_id}/history
  → Returns full conversation from PostgreSQL (persisted on each turn)
  → STM is cache; PostgreSQL is source of truth for history
```

---

## 3. Multi-Tenant & Session Design

### Tenant Hierarchy

```
SUPER_ADMIN (platform-level)
    │
    ├── Tenant A (company: "Acme Legal")
    │     ├── CLIENT_ADMIN (manages Tenant A)
    │     ├── CLIENT_USER (end users of Tenant A chatbot)
    │     ├── Collections: ["legal-docs", "hr-policy", "contracts-2024"]
    │     ├── Qdrant Collection: tenant_<tenant_a_id>
    │     └── Sessions: per user of Tenant A
    │
    └── Tenant B (company: "TechCorp")
          ├── CLIENT_ADMIN
          ├── CLIENT_USER
          ├── Collections: ["product-docs", "support-kb"]
          ├── Qdrant Collection: tenant_<tenant_b_id>
          └── Sessions: per user of Tenant B
```

### Isolation Guarantees

| Layer | Isolation Mechanism |
|---|---|
| API | JWT contains `tenant_id`; middleware injects into ContextVar |
| PostgreSQL | Every table has `tenant_id` column; all queries filter by it |
| Qdrant | Separate collection per tenant (`tenant_{id}`) + payload filter |
| Redis | All keys namespaced: `{tenant_id}:{key_type}:{id}` |
| S3 | All objects under `s3://bucket/{tenant_id}/` prefix |
| Celery | Tasks carry `tenant_id`; workers validate before processing |
| LangSmith | All traces tagged with `tenant_id` metadata |

### Roles & Permissions

| Action | SUPER_ADMIN | CLIENT_ADMIN | CLIENT_USER |
|---|---|---|---|
| Create/delete tenant | ✓ | ✗ | ✗ |
| Create/delete collection | ✓ | ✓ (own tenant) | ✗ |
| Upload documents | ✓ | ✓ (own tenant) | ✗ |
| Delete documents | ✓ | ✓ (own tenant) | ✗ |
| Configure tenant (prompts, LLM, guardrails) | ✓ | ✓ (own tenant) | ✗ |
| Chat | ✓ | ✓ | ✓ |
| View session history | ✓ | ✓ (own tenant) | ✓ (own sessions) |
| View analytics | ✓ | ✓ (own tenant) | ✗ |

---

## 4. Dynamic Per-Client Configuration

Every aspect of the RAG pipeline is configurable per tenant and stored in PostgreSQL `tenant_configs` table. No hardcoded values.

```json
{
  "tenant_id": "t_abc",
  "company_name": "Acme Legal",
  "branding": {
    "bot_name": "LexBot",
    "welcome_message": "Hello! I'm LexBot, your legal document assistant."
  },
  "llm": {
    "provider": "openai",
    "model": "gpt-4o",
    "temperature": 0.1,
    "max_tokens": 1500,
    "timeout_seconds": 30
  },
  "prompts": {
    "system_prompt_id": "lc:legal-assistant-v3:stable",
    "prompt_variables": {
      "company_name": "Acme Legal",
      "jurisdiction": "US Federal",
      "tone": "formal"
    },
    "rag_prompt_id": "lc:rag-context-v2:stable"
  },
  "retrieval": {
    "top_k": 5,
    "similarity_threshold": 0.72,
    "hybrid_alpha": 0.6,
    "reranker_enabled": true,
    "reranker_model": "cohere-rerank-v3",
    "hyde_enabled": true,
    "multi_query_enabled": true,
    "query_expansion_count": 3
  },
  "memory": {
    "stm_window_turns": 10,
    "stm_ttl_days": 7,
    "ltm_enabled": true,
    "ltm_summarize_every_n_turns": 20,
    "ltm_max_memories": 50
  },
  "guardrails": {
    "input": {
      "pii_detection": true,
      "pii_action": "mask",
      "toxicity_filter": true,
      "prompt_injection": true,
      "topic_restriction_enabled": true,
      "allowed_topics": ["legal", "contracts", "compliance", "hr"]
    },
    "output": {
      "pii_scrub": true,
      "hallucination_check": true,
      "hallucination_threshold": 0.5,
      "citation_validation": true
    }
  },
  "ingestion": {
    "allowed_mime_types": ["application/pdf", "image/jpeg", "image/png", "text/csv"],
    "max_file_size_mb": 50,
    "ocr_engine": "tesseract",
    "embedding_model": "text-embedding-3-large",
    "chunk_size_tokens": 512,
    "chunk_overlap_tokens": 64
  },
  "rate_limits": {
    "upload_per_day": 100,
    "chat_requests_per_minute": 60,
    "chat_requests_per_day": 5000,
    "max_concurrent_sessions": 200
  },
  "caching": {
    "llm_response_cache_enabled": true,
    "llm_response_cache_ttl_seconds": 3600
  },
  "notifications": {
    "webhook_url": "https://acme.com/webhooks/rag",
    "notify_on": ["ingestion_completed", "ingestion_failed"]
  }
}
```

---

## 5. Database Schema

### PostgreSQL Tables

```sql
-- Tenants
CREATE TABLE tenants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(255) NOT NULL,
    slug            VARCHAR(100) UNIQUE NOT NULL,   -- URL-safe identifier
    status          VARCHAR(20) DEFAULT 'active',   -- active | suspended | deleted
    plan            VARCHAR(50) DEFAULT 'starter',  -- starter | pro | enterprise
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Tenant Configuration (one row per tenant, JSON blob for flexibility)
CREATE TABLE tenant_configs (
    tenant_id       UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    config          JSONB NOT NULL DEFAULT '{}',
    updated_at      TIMESTAMPTZ DEFAULT now(),
    updated_by      UUID  -- user_id who last changed config
);

-- Users
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(30) NOT NULL,  -- super_admin | client_admin | client_user
    first_name      VARCHAR(100),
    last_name       VARCHAR(100),
    is_active       BOOLEAN DEFAULT true,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, email)
);
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email ON users(email);

-- Collections (logical grouping of documents per tenant)
CREATE TABLE collections (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    schema_hints    JSONB DEFAULT '{}',  -- for CSV/Excel verbalization
    status          VARCHAR(20) DEFAULT 'active',
    document_count  INT DEFAULT 0,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    UNIQUE(tenant_id, name)
);
CREATE INDEX idx_collections_tenant ON collections(tenant_id);

-- Documents (metadata only — content lives in S3 + Qdrant)
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    collection_id   UUID NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    filename        VARCHAR(500) NOT NULL,
    s3_key          TEXT NOT NULL,
    mime_type       VARCHAR(100) NOT NULL,
    file_size_bytes BIGINT,
    sha256          VARCHAR(64) NOT NULL,
    chunk_count     INT DEFAULT 0,
    status          VARCHAR(20) DEFAULT 'pending',  -- pending|indexed|deleted|failed
    upload_metadata JSONB DEFAULT '{}',
    uploaded_by     UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now(),
    indexed_at      TIMESTAMPTZ,
    deleted_at      TIMESTAMPTZ,   -- soft delete
    UNIQUE(tenant_id, sha256)      -- deduplication per tenant
);
CREATE INDEX idx_documents_tenant ON documents(tenant_id);
CREATE INDEX idx_documents_collection ON documents(collection_id);
CREATE INDEX idx_documents_status ON documents(status);

-- Ingestion Jobs
CREATE TABLE ingestion_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL REFERENCES tenants(id),
    status          VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    -- PENDING|QUEUED|DOWNLOADING|CLASSIFYING|PARSING|CHUNKING|EMBEDDING|INDEXING|COMPLETED|FAILED
    progress_pct    INT DEFAULT 0,
    chunk_count     INT,
    error_message   TEXT,
    error_stack     TEXT,
    attempt_count   INT DEFAULT 0,
    celery_task_id  VARCHAR(255),
    created_at      TIMESTAMPTZ DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ
);
CREATE INDEX idx_jobs_document ON ingestion_jobs(document_id);
CREATE INDEX idx_jobs_tenant ON ingestion_jobs(tenant_id);
CREATE INDEX idx_jobs_status ON ingestion_jobs(status);

-- Sessions
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          VARCHAR(20) DEFAULT 'active',  -- active | ended | expired
    config_snapshot JSONB NOT NULL,  -- tenant config at session creation time
    turn_count      INT DEFAULT 0,
    last_active_at  TIMESTAMPTZ DEFAULT now(),
    created_at      TIMESTAMPTZ DEFAULT now(),
    ended_at        TIMESTAMPTZ
);
CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_tenant ON sessions(tenant_id);
CREATE INDEX idx_sessions_status ON sessions(status);

-- Messages (persistent conversation history)
CREATE TABLE messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    tenant_id       UUID NOT NULL,
    user_id         UUID NOT NULL,
    role            VARCHAR(20) NOT NULL,  -- user | assistant | system
    content         TEXT NOT NULL,
    sources         JSONB DEFAULT '[]',   -- retrieved chunk references
    usage           JSONB DEFAULT '{}',   -- token counts
    cached          BOOLEAN DEFAULT false,
    guardrail_flags JSONB DEFAULT '{}',   -- which guardrails triggered
    created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_messages_session ON messages(session_id);
CREATE INDEX idx_messages_tenant ON messages(tenant_id);

-- Refresh Tokens
CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      VARCHAR(255) UNIQUE NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked         BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

### Qdrant Collections

```
Per-tenant document collection:
  Name:    tenant_{tenant_id}
  Vectors: {size: 1536, distance: Cosine}  ← text-embedding-3-large
  Sparse:  {index: BM25}                   ← for hybrid search
  Payload schema per point:
    tenant_id, document_id, collection_id, chunk_index, chunk_id,
    text, doc_type, source_filename, page_num (optional),
    keywords[], quality (high|low), created_at, sha256,
    start_time_sec (audio/video only), ocr_confidence (scanned only)

Per-tenant LTM collection:
  Name:    ltm_{tenant_id}
  Vectors: {size: 1536, distance: Cosine}
  Payload schema:
    user_id, session_id, summary_text, turn_range_start,
    turn_range_end, created_at, topics[], preferences[]
```

---

## 6. API Contract

### Authentication
```
POST   /v1/auth/login              # {email, password} → {access_token, refresh_token}
POST   /v1/auth/refresh            # {refresh_token} → {access_token}
POST   /v1/auth/logout             # revoke refresh token
GET    /v1/auth/me                 # current user profile
```

### Tenant Management (SUPER_ADMIN only)
```
GET    /v1/tenants                 # list all tenants
POST   /v1/tenants                 # create tenant
GET    /v1/tenants/{id}            # get tenant details
PATCH  /v1/tenants/{id}            # update tenant
DELETE /v1/tenants/{id}            # deactivate tenant
GET    /v1/tenants/{id}/config     # get tenant config
PUT    /v1/tenants/{id}/config     # replace full config
PATCH  /v1/tenants/{id}/config     # update partial config
```

### Collections (CLIENT_ADMIN + SUPER_ADMIN)
```
GET    /v1/collections             # list tenant's collections
POST   /v1/collections             # create collection
GET    /v1/collections/{id}        # collection details + stats
PATCH  /v1/collections/{id}        # update collection
DELETE /v1/collections/{id}        # delete collection + all docs
```

### Ingestion (CLIENT_ADMIN + SUPER_ADMIN)
```
POST   /v1/ingest/upload           # upload file → job_id
GET    /v1/ingest/status/{job_id}  # poll job status + progress
GET    /v1/ingest/jobs             # list all jobs for tenant
POST   /v1/ingest/retry/{job_id}   # retry failed job
```

### Documents (CLIENT_ADMIN + SUPER_ADMIN)
```
GET    /v1/documents               # list documents (?collection_id=, ?status=)
GET    /v1/documents/{id}          # document details
DELETE /v1/documents/{id}          # delete doc from S3 + Qdrant + soft-delete PG
GET    /v1/documents/{id}/chunks   # list indexed chunks (debug/audit)
```

### Sessions (all roles)
```
POST   /v1/sessions                # create new session → session_id
GET    /v1/sessions                # list user's sessions
GET    /v1/sessions/{id}           # session details
DELETE /v1/sessions/{id}           # end session
GET    /v1/sessions/{id}/history   # full conversation history
```

### Chat (all roles)
```
POST   /v1/chat/completions        # REST chat (full response)
WS     /v1/ws/chat/{session_id}    # WebSocket streaming chat
GET    /v2/chat/stream             # SSE streaming chat (v2)
```

### Health & Metrics
```
GET    /health                     # liveness probe
GET    /health/ready               # readiness probe (checks PG, Redis, Qdrant)
GET    /metrics                    # Prometheus scrape endpoint
```

---

## 7. Project Directory Tree

```
Production_Grade_RAGbot/
├── IMPLEMENTATION.md              ← this file
├── .env.example
├── .env                           ← gitignored
├── .gitignore
├── .pre-commit-config.yaml
├── Makefile
├── pyproject.toml
│
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   └── prod.txt
│
├── infra/
│   ├── docker-compose.yml
│   ├── docker-compose.test.yml
│   ├── nginx/
│   │   └── nginx.conf
│   ├── grafana/
│   │   ├── provisioning/
│   │   │   ├── dashboards.yml
│   │   │   └── datasources.yml
│   │   └── dashboards/
│   │       ├── api_overview.json
│   │       ├── celery_workers.json
│   │       ├── rag_pipeline.json
│   │       └── llm_costs.json
│   ├── prometheus/
│   │   └── prometheus.yml
│   └── rabbitmq/
│       └── rabbitmq.conf
│
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── dependencies.py
│   │   ├── v1/
│   │   │   ├── __init__.py
│   │   │   ├── router.py
│   │   │   ├── routers/
│   │   │   │   ├── auth.py
│   │   │   │   ├── tenants.py
│   │   │   │   ├── collections.py
│   │   │   │   ├── ingestion.py
│   │   │   │   ├── documents.py
│   │   │   │   ├── sessions.py
│   │   │   │   ├── chat.py
│   │   │   │   ├── websocket.py
│   │   │   │   └── health.py
│   │   │   ├── schemas/
│   │   │   │   ├── auth.py
│   │   │   │   ├── tenant.py
│   │   │   │   ├── collection.py
│   │   │   │   ├── ingestion.py
│   │   │   │   ├── document.py
│   │   │   │   ├── session.py
│   │   │   │   └── chat.py
│   │   │   └── middleware/
│   │   │       ├── auth_middleware.py
│   │   │       ├── rate_limit.py
│   │   │       ├── request_id.py
│   │   │       └── tenant_context.py
│   │   └── v2/
│   │       ├── __init__.py
│   │       ├── router.py
│   │       └── routers/
│   │           └── chat.py
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── exceptions.py
│   │   ├── security.py
│   │   └── constants.py
│   │
│   ├── domain/
│   │   ├── entities/
│   │   │   ├── tenant.py
│   │   │   ├── user.py
│   │   │   ├── document.py
│   │   │   ├── session.py
│   │   │   └── job.py
│   │   └── value_objects/
│   │       ├── tenant_id.py
│   │       ├── embedding.py
│   │       └── chunk.py
│   │
│   ├── services/
│   │   ├── ingestion/
│   │   │   ├── ingestion_service.py
│   │   │   ├── parsers/
│   │   │   │   ├── base.py
│   │   │   │   ├── pdf_parser.py
│   │   │   │   ├── image_parser.py
│   │   │   │   ├── excel_parser.py
│   │   │   │   ├── csv_parser.py
│   │   │   │   ├── audio_parser.py
│   │   │   │   ├── video_parser.py
│   │   │   │   ├── docx_parser.py
│   │   │   │   └── factory.py
│   │   │   ├── chunkers/
│   │   │   │   ├── base.py
│   │   │   │   ├── recursive_chunker.py
│   │   │   │   ├── semantic_chunker.py
│   │   │   │   ├── table_chunker.py
│   │   │   │   └── factory.py
│   │   │   └── enrichers/
│   │   │       ├── base.py
│   │   │       ├── metadata_enricher.py
│   │   │       └── keyword_enricher.py
│   │   │
│   │   ├── embedding/
│   │   │   ├── embedding_service.py
│   │   │   └── providers/
│   │   │       ├── base.py
│   │   │       ├── openai_provider.py
│   │   │       ├── cohere_provider.py
│   │   │       └── factory.py
│   │   │
│   │   ├── retrieval/
│   │   │   ├── retrieval_service.py
│   │   │   ├── retrievers/
│   │   │   │   ├── base.py
│   │   │   │   ├── dense_retriever.py
│   │   │   │   ├── sparse_retriever.py
│   │   │   │   └── ensemble_retriever.py
│   │   │   ├── rerankers/
│   │   │   │   ├── base.py
│   │   │   │   ├── cohere_reranker.py
│   │   │   │   └── cross_encoder_reranker.py
│   │   │   └── filters/
│   │   │       ├── metadata_filter.py
│   │   │       └── query_rewriter.py
│   │   │
│   │   ├── llm/
│   │   │   ├── llm_service.py
│   │   │   ├── prompt_manager.py
│   │   │   ├── response_cache.py
│   │   │   └── providers/
│   │   │       ├── base.py
│   │   │       ├── openai_provider.py
│   │   │       ├── anthropic_provider.py
│   │   │       └── factory.py
│   │   │
│   │   ├── memory/
│   │   │   ├── memory_service.py
│   │   │   ├── short_term/
│   │   │   │   └── redis_stm.py
│   │   │   └── long_term/
│   │   │       ├── ltm_service.py
│   │   │       └── qdrant_ltm.py
│   │   │
│   │   ├── guardrails/
│   │   │   ├── guardrail_service.py
│   │   │   ├── input/
│   │   │   │   ├── base.py
│   │   │   │   ├── pii_detector.py
│   │   │   │   ├── toxicity_filter.py
│   │   │   │   ├── prompt_injection.py
│   │   │   │   └── topic_classifier.py
│   │   │   └── output/
│   │   │       ├── base.py
│   │   │       ├── hallucination_check.py
│   │   │       ├── pii_scrubber.py
│   │   │       └── citation_validator.py
│   │   │
│   │   ├── chat/
│   │   │   └── chat_service.py
│   │   │
│   │   ├── session/
│   │   │   └── session_service.py
│   │   │
│   │   └── tenant/
│   │       └── tenant_service.py
│   │
│   ├── infrastructure/
│   │   ├── database/
│   │   │   ├── postgres/
│   │   │   │   ├── connection.py
│   │   │   │   ├── models/
│   │   │   │   │   ├── base.py
│   │   │   │   │   ├── tenant.py
│   │   │   │   │   ├── user.py
│   │   │   │   │   ├── collection.py
│   │   │   │   │   ├── document.py
│   │   │   │   │   ├── job.py
│   │   │   │   │   ├── session.py
│   │   │   │   │   └── message.py
│   │   │   │   └── migrations/
│   │   │   │       ├── env.py
│   │   │   │       ├── script.py.mako
│   │   │   │       └── versions/
│   │   │   └── redis/
│   │   │       └── connection.py
│   │   ├── repositories/
│   │   │   ├── base.py
│   │   │   ├── tenant_repository.py
│   │   │   ├── user_repository.py
│   │   │   ├── collection_repository.py
│   │   │   ├── document_repository.py
│   │   │   ├── job_repository.py
│   │   │   ├── session_repository.py
│   │   │   └── message_repository.py
│   │   ├── vector_store/
│   │   │   ├── base.py
│   │   │   ├── qdrant_store.py
│   │   │   └── qdrant_client.py
│   │   ├── storage/
│   │   │   ├── base.py
│   │   │   └── s3_storage.py
│   │   ├── message_queue/
│   │   │   ├── base.py
│   │   │   ├── rabbitmq_publisher.py
│   │   │   └── celery_app.py
│   │   └── observability/
│   │       ├── langsmith_client.py
│   │       ├── prometheus_metrics.py
│   │       └── tracing.py
│   │
│   └── workers/
│       ├── ingestion_worker.py
│       ├── ltm_worker.py
│       └── cleanup_worker.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── services/
│   │   │   ├── test_ingestion_service.py
│   │   │   ├── test_retrieval_service.py
│   │   │   ├── test_chat_service.py
│   │   │   ├── test_guardrail_service.py
│   │   │   └── test_memory_service.py
│   │   └── parsers/
│   │       ├── test_pdf_parser.py
│   │       ├── test_image_parser.py
│   │       └── test_csv_parser.py
│   ├── integration/
│   │   ├── test_ingestion_api.py
│   │   ├── test_chat_api.py
│   │   ├── test_auth_flow.py
│   │   └── test_websocket.py
│   └── golden_datasets/
│       └── qa_pairs_sample.jsonl
│
└── scripts/
    ├── seed_dev_data.py
    ├── create_tenant.py
    ├── migrate.sh
    └── benchmark_retrieval.py
```

---

## 8. Daily Implementation Plan

> Each day = ~6–8 hours of focused work.  
> **Dependencies** are listed so you know what must be done first.  
> **Verification** tells you exactly how to confirm the day's work is correct.

---

### MODULE 1 — Foundation & Infrastructure (Days 1–5)

---

#### DAY 1 — Project Skeleton + Config + Docker Compose

**Goal:** Running infrastructure (Postgres, Redis, RabbitMQ, Qdrant) + FastAPI boots.

**Files to create:**
- `pyproject.toml` — ruff, mypy, pytest config
- `requirements/base.txt` — fastapi, uvicorn, sqlalchemy, asyncpg, pydantic-settings, aioredis, celery, aio-pika, qdrant-client, boto3, structlog, prometheus-fastapi-instrumentator
- `requirements/dev.txt` — pytest, httpx, pytest-asyncio, testcontainers, factory-boy
- `.env.example` — all vars documented
- `src/core/config.py` — Pydantic BaseSettings
- `src/api/main.py` — FastAPI app factory with lifespan stub
- `src/api/v1/routers/health.py` — /health, /health/ready
- `infra/docker-compose.yml` — postgres:16, redis:7, rabbitmq:3-management, qdrant:latest, adminer
- `Makefile` — targets: dev, test, migrate, lint, worker

**Key implementation notes:**
- `config.py`: ALL secrets from env vars. Use `@lru_cache` on settings instance.
- `main.py`: Use `@asynccontextmanager` lifespan — init DB pool, Redis, Qdrant client on startup.
- `/health/ready`: Check all 3 dependencies respond before returning 200.

**Verification:**
```bash
make dev          # docker-compose up
curl localhost:8000/health/ready  # should return {"status": "ok"}
# RabbitMQ UI: localhost:15672 (guest/guest)
# Adminer: localhost:8080 (postgres connection)
```

---

#### DAY 2 — Database Models + Alembic Migrations

**Dependencies:** Day 1 complete, docker-compose running.

**Files to create:**
- `src/infrastructure/database/postgres/connection.py` — async engine, session factory
- `src/infrastructure/database/postgres/models/base.py` — declarative base
- `src/infrastructure/database/postgres/models/tenant.py`
- `src/infrastructure/database/postgres/models/user.py`
- `src/infrastructure/database/postgres/models/collection.py`
- `src/infrastructure/database/postgres/models/document.py`
- `src/infrastructure/database/postgres/models/job.py`
- `src/infrastructure/database/postgres/models/session.py`
- `src/infrastructure/database/postgres/models/message.py`
- `src/infrastructure/database/postgres/migrations/env.py`
- `src/infrastructure/database/postgres/migrations/versions/001_initial_schema.py`
- `scripts/migrate.sh`

**Key implementation notes:**
- All models inherit `TimestampMixin` (created_at, updated_at with auto-update).
- All tables have `tenant_id` indexed.
- Use `JSONB` for `config`, `upload_metadata`, `sources`, `guardrail_flags`.
- Alembic `env.py`: use async engine for `run_async_migrations`.

**Verification:**
```bash
make migrate      # alembic upgrade head
# Check Adminer: all 8 tables created with correct columns and indexes
```

---

#### DAY 3 — Auth System (JWT + RBAC)

**Dependencies:** Day 2 complete.

**Files to create:**
- `src/core/security.py` — JWT encode/decode, bcrypt hash/verify
- `src/core/exceptions.py` — AuthError, PermissionError, TenantNotFoundError, etc.
- `src/infrastructure/repositories/base.py` — generic IRepository ABC
- `src/infrastructure/repositories/tenant_repository.py`
- `src/infrastructure/repositories/user_repository.py`
- `src/services/tenant/tenant_service.py`
- `src/api/v1/schemas/auth.py` — LoginRequest, TokenResponse
- `src/api/v1/schemas/tenant.py`
- `src/api/v1/routers/auth.py` — POST /login, /refresh, /logout, GET /me
- `src/api/v1/routers/tenants.py` — CRUD
- `src/api/v1/middleware/tenant_context.py` — ContextVar injection
- `src/api/v1/middleware/auth_middleware.py` — JWT validation
- `src/api/v1/middleware/request_id.py`
- `src/api/dependencies.py` — get_current_user, require_role(), get_db, get_tenant_config
- `scripts/seed_dev_data.py` — create super_admin + 2 test tenants

**Key implementation notes:**
- JWT payload: `{sub: user_id, tenant_id, role, exp}`. Sign with RS256 (asymmetric) for production.
- `require_role(*roles)` returns a FastAPI dependency that checks `current_user.role in roles`.
- `tenant_context.py`: After JWT decode, load tenant from DB → store in `ContextVar[TenantContext]`.
- Refresh tokens: store hashed in `refresh_tokens` table. Rotation on every refresh.

**Verification:**
```bash
python scripts/seed_dev_data.py
curl -X POST localhost:8000/v1/auth/login \
  -d '{"email":"admin@tenant1.com","password":"test123"}'
# Should return access_token + refresh_token
curl -H "Authorization: Bearer <token>" localhost:8000/v1/auth/me
# Should return user profile
```

---

#### DAY 4 — Redis + Rate Limiter + Collection CRUD

**Dependencies:** Day 3 complete.

**Files to create:**
- `src/infrastructure/database/redis/connection.py` — aioredis pool
- `src/api/v1/middleware/rate_limit.py` — sliding window Lua script
- `src/infrastructure/repositories/collection_repository.py`
- `src/api/v1/schemas/collection.py`
- `src/api/v1/routers/collections.py`
- `src/api/v1/router.py` — aggregate all v1 routers

**Key implementation notes:**
- Rate limiter Lua script runs atomically: `INCR + EXPIRE` in one operation.
- Two rate limit types: per-minute (chat) and per-day (uploads). Both from tenant config.
- Rate limit headers in response: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

**Verification:**
```bash
# Create collection
curl -X POST localhost:8000/v1/collections \
  -H "Authorization: Bearer <token>" \
  -d '{"name":"test-docs","description":"test"}'
# Spam endpoint to trigger rate limit → should get 429 after limit
```

---

#### DAY 5 — S3 Storage + Qdrant Client + Celery App

**Dependencies:** Days 1-4 complete.

**Files to create:**
- `src/infrastructure/storage/base.py` — IFileStorage ABC
- `src/infrastructure/storage/s3_storage.py` — aioboto3, presigned URLs
- `src/infrastructure/vector_store/base.py` — IVectorStore ABC
- `src/infrastructure/vector_store/qdrant_client.py` — singleton async client
- `src/infrastructure/vector_store/qdrant_store.py` — create_collection, upsert, search, delete
- `src/infrastructure/message_queue/celery_app.py` — queue routing config
- `src/infrastructure/message_queue/rabbitmq_publisher.py` — aio-pika with confirm mode

**Key implementation notes:**
- `qdrant_store.create_collection_if_not_exists(tenant_id)`: Called on tenant creation and on first upload. Idempotent.
- Qdrant collection config: vectors size=1536, distance=Cosine. Enable sparse vectors for hybrid.
- S3 storage: use aioboto3 async context manager. Generate presigned download URLs (TTL 1 hour) for secure file access.
- Celery queues: `ingestion.documents`, `ingestion.images`, `ingestion.tabular`, `ingestion.media`, `ingestion.dlq`.

**Verification:**
```bash
# Test S3 upload (use LocalStack locally)
python -c "from src.infrastructure.storage.s3_storage import S3Storage; ..."
# Test Qdrant collection creation
python -c "from src.infrastructure.vector_store.qdrant_store import QdrantStore; ..."
# Check Qdrant dashboard: localhost:6333/dashboard
```

---

### MODULE 2 — Ingestion Pipeline (Days 6–13)

---

#### DAY 6 — Ingestion API + Job Tracking

**Dependencies:** Module 1 complete.

**Files to create:**
- `src/infrastructure/repositories/document_repository.py`
- `src/infrastructure/repositories/job_repository.py`
- `src/services/ingestion/ingestion_service.py`
- `src/api/v1/schemas/ingestion.py` — UploadResponse, JobStatusResponse
- `src/api/v1/schemas/document.py`
- `src/api/v1/routers/ingestion.py` — POST /upload, GET /status/{job_id}, GET /jobs
- `src/api/v1/routers/documents.py` — GET /documents, GET /{id}, DELETE /{id}

**Key implementation notes:**
- `ingestion_service.upload()`: validate → S3 → INSERT document → INSERT job → publish RMQ → return job_id. All in try/except; if RMQ publish fails, update job to FAILED (don't leave orphaned).
- `DELETE /documents/{id}`: Delete in order: Qdrant (by payload filter) → S3 → soft-delete PostgreSQL. If Qdrant delete fails, abort (still recoverable). If S3 fails after Qdrant, log for manual cleanup.
- Job status polling includes `progress_pct` so frontend can show progress bar.

**Verification:**
```bash
curl -X POST localhost:8000/v1/ingest/upload \
  -H "Authorization: Bearer <admin_token>" \
  -F "file=@sample.pdf" \
  -F "collection_id=<coll_id>"
# Returns {job_id, document_id, status: "QUEUED"}
curl localhost:8000/v1/ingest/status/<job_id>
# Returns current status
```

---

#### DAY 7 — Parser Infrastructure + PDF Digital Parser

**Dependencies:** Day 6 complete.

**Files to create:**
- `src/domain/value_objects/chunk.py` — ParsedPage, DocumentChunk dataclasses
- `src/services/ingestion/parsers/base.py` — IDocumentParser ABC
- `src/services/ingestion/parsers/pdf_parser.py`
  - `classify_pdf(path)` → per-page {type, char_count, image_count}
  - `extract_digital_page(path, page_num)` → pdfplumber
  - `extract_tables_from_page(page)` → separate table chunks
  - Full `PDFParser.parse()` routing per page

**Key implementation notes:**
- `IDocumentParser.parse()` is `async def` — VLM calls inside are awaitable.
- `classify_pdf`: char_count > 50 → digital; has images + no text → scanned; both → mixed.
- pdfplumber table extraction: convert each row to `"col1 | col2 | col3"` format. Store table as separate `ParsedPage` with `content_type="table"`.
- Every `ParsedPage` carries: `{text, page_num, content_type, source_path, char_count}`.

**Verification:**
```bash
python -c "
from src.services.ingestion.parsers.pdf_parser import PDFParser
import asyncio
chunks = asyncio.run(PDFParser().parse('tests/fixtures/digital.pdf', 'doc1', 'tenant1'))
print(len(chunks), chunks[0].text[:200])
"
```

---

#### DAY 8 — Scanned PDF (OCR) + Mixed PDF Parser

**Dependencies:** Day 7 complete. Tesseract installed (`apt install tesseract-ocr`).

**Files to create/extend:**
- `src/services/ingestion/parsers/pdf_parser.py` — add OCR path
  - `preprocess_image_for_ocr(pil_image)` — deskew + adaptive threshold + denoise
  - `ocr_page(path, page_num, dpi=300)` → text + confidence
  - `_route_page(page_info)` → digital | scanned path per page
  - Mixed PDF: call `_route_page` per page, merge results in page order

**Key implementation notes:**
- Use `pdf2image.convert_from_path(path, dpi=300, first_page=n, last_page=n)` for single-page extraction (memory efficient).
- OCR confidence gate: < 50 → skip + flag `needs_review=True` + log warning. 50-70 → index with `quality="low"`. > 70 → `quality="high"`.
- Never embed pages with char_count < 50 after OCR — they produce useless vectors.
- Store `ocr_confidence` in chunk metadata for Qdrant payload filtering.

**Verification:**
```bash
python -c "
from src.services.ingestion.parsers.pdf_parser import PDFParser
import asyncio
# Use a real scanned PDF as fixture
chunks = asyncio.run(PDFParser().parse('tests/fixtures/scanned.pdf', 'doc2', 'tenant1'))
for c in chunks:
    print(c.metadata.get('page'), c.metadata.get('ocr_confidence'), c.text[:100])
"
```

---

#### DAY 9 — Image Parser (VLM) + Embedded Images in PDFs

**Dependencies:** Day 8, OpenAI API key.

**Files to create:**
- `src/services/ingestion/parsers/image_parser.py`
  - `caption_image(img_bytes, ext)` → GPT-4o vision description
  - `ImageParser.parse()` → VLM caption as single chunk
  - Async semaphore: max 5 concurrent VLM calls
  - Size gate: skip images < 100x100 pixels
  - Hash dedup: skip if sha256(img_bytes) seen in current document
- Extend `src/services/ingestion/parsers/pdf_parser.py`:
  - `extract_embedded_images(path, page_num)` → calls `caption_image()` for each image

**Key implementation notes:**
- VLM prompt is carefully structured (from reference doc section 2.4).
- Semaphore prevents overwhelming OpenAI rate limits: `asyncio.Semaphore(5)`.
- Image chunk `content_type = "embedded_image"`, metadata includes `dimensions`, `page_num`, `image_index`.
- For standalone images (JPG/PNG uploads): single chunk with VLM caption as full content.

**Verification:**
```bash
python -c "
from src.services.ingestion.parsers.image_parser import ImageParser
import asyncio
chunks = asyncio.run(ImageParser().parse('tests/fixtures/chart.png', 'doc3', 'tenant1'))
print(chunks[0].text[:500])  # Should be VLM description of chart
"
```

---

#### DAY 10 — CSV + Excel Parsers

**Dependencies:** Day 7 complete.

**Files to create:**
- `src/services/ingestion/parsers/csv_parser.py`
  - `verbalize_row(row, schema_hints)` → "Record — col: val, col: val"
  - `verbalize_column_stats(df)` → statistical summary chunks
  - `CSVParser.parse()` → row chunks + stats chunks
- `src/services/ingestion/parsers/excel_parser.py`
  - Per-sheet extraction: sheet name + headers + rows
  - Each sheet → separate set of chunks with `sheet_name` in metadata
  - `ExcelParser.parse()` → verbalized row chunks per sheet

**Key implementation notes:**
- Schema hints come from `collection.schema_hints` (set by CLIENT_ADMIN at collection creation). Parser receives them via `document_metadata`.
- CSV streaming: use `pd.read_csv(path, chunksize=1000)` for large files — don't load entire file into memory.
- Excel: skip empty sheets. Mark `content_type="excel_row"` or `"excel_stats"`.
- Both produce `verbalized` text — not raw `col1,col2` CSV. Embeddings of verbalized text retrieve correctly.

**Verification:**
```bash
python -c "
from src.services.ingestion.parsers.csv_parser import CSVParser
import asyncio
chunks = asyncio.run(CSVParser().parse('tests/fixtures/sales_data.csv', 'doc4', 'tenant1'))
print(chunks[:3])  # Should be: 'Record — Product: X, Revenue: 50000, Region: US'
"
```

---

#### DAY 11 — Audio + Video Parsers

**Dependencies:** Day 7, Whisper installed.

**Files to create:**
- `src/services/ingestion/parsers/audio_parser.py`
  - Whisper model as class-level singleton (load once, reuse)
  - `transcribe(audio_path)` → Whisper segments with timestamps
  - `group_segments(segments, target_words=200)` → grouped chunks
  - `AudioParser.parse()` → transcript chunks with `start_time_sec`, `end_time_sec`
- `src/services/ingestion/parsers/video_parser.py`
  - `extract_audio(video_path)` → ffmpeg subprocess → temp mp3
  - `extract_keyframes(video_path, interval_sec=60)` → PIL images
  - `VideoParser.parse()` → audio transcription + keyframe VLM captions (aligned by timestamp)

**Key implementation notes:**
- Whisper model: load `whisper.load_model("base")` once in `__init_subclass__` or class var — NOT inside `parse()`. Loading model per task = huge slowdown.
- Video: `ffmpeg -i input.mp4 -vn -acodec mp3 output.mp3` for audio extraction. Use `subprocess.run()` (not asyncio subprocess — it's CPU-bound).
- Keyframe captions are aligned to nearest transcript segment by timestamp → merged chunk.
- `content_type = "audio_transcript"` or `"video_transcript"`.

**Verification:**
```bash
python -c "
from src.services.ingestion.parsers.audio_parser import AudioParser
import asyncio
chunks = asyncio.run(AudioParser().parse('tests/fixtures/sample.mp3', 'doc5', 'tenant1'))
for c in chunks[:3]:
    print(c.metadata['start_time_sec'], c.text[:100])
"
```

---

#### DAY 12 — Parser Factory + Chunkers + Enrichers

**Dependencies:** Days 7-11 complete.

**Files to create:**
- `src/services/ingestion/parsers/factory.py` — ParserFactory
- `src/services/ingestion/chunkers/base.py` — IChunker ABC
- `src/services/ingestion/chunkers/recursive_chunker.py` — LangChain RecursiveCharacterTextSplitter
- `src/services/ingestion/chunkers/table_chunker.py` — header in every chunk
- `src/services/ingestion/chunkers/factory.py` — ChunkerFactory
- `src/services/ingestion/enrichers/base.py` — IChunkEnricher ABC
- `src/services/ingestion/enrichers/metadata_enricher.py` — inject all metadata fields
- `src/services/ingestion/enrichers/keyword_enricher.py` — YAKE keyword extraction

**Key implementation notes:**
- `ParserFactory.get_parser(mime_type, pdf_classification=None)`:
  - `application/pdf` + `pdf_classification` → `PDFParser`
  - `image/*` → `ImageParser`
  - `text/csv` → `CSVParser`
  - `application/vnd.*excel*`, `application/vnd.openxmlformats*` → `ExcelParser`
  - `audio/*` → `AudioParser`
  - `video/*` → `VideoParser`
- `ChunkerFactory.get_chunker(content_type)`:
  - `"table"`, `"excel_row"`, `"csv_row"` → `TableChunker` (no further splitting)
  - `"audio_transcript"`, `"video_transcript"` → no-op (already chunked during parsing)
  - everything else → `RecursiveChunker`
- `KeywordEnricher`: YAKE top-10 keywords per chunk stored as `keywords` array in metadata.

**Verification:**
```bash
python -c "
from src.services.ingestion.parsers.factory import ParserFactory
from src.services.ingestion.chunkers.factory import ChunkerFactory
p = ParserFactory.get_parser('application/pdf', {'pdf_type': 'digital'})
print(type(p).__name__)  # PDFParser
c = ChunkerFactory.get_chunker('digital_pdf')
print(type(c).__name__)  # RecursiveChunker
"
```

---

#### DAY 13 — Celery Worker (Full Pipeline)

**Dependencies:** Days 6-12 complete.

**Files to create:**
- `src/services/embedding/embedding_service.py` — batched embedding, retry on rate limit
- `src/services/embedding/providers/openai_provider.py`
- `src/services/embedding/providers/factory.py`
- `src/workers/ingestion_worker.py` — full Celery task

**Key implementation notes:**
- Worker task structure:
  1. Update job status at each step (DOWNLOADING → CLASSIFYING → ... → COMPLETED)
  2. Each step wrapped in try/except — transient errors retry, permanent errors → FAILED
  3. `acks_late=True, reject_on_worker_lost=True` on task decorator
  4. Cleanup: always delete `/tmp/{job_id}/` in `finally` block
- `EmbeddingService.embed_batch()`: batch size 100, Tenacity retry with exponential backoff on `RateLimitError`. Store `model_id` in every chunk metadata.
- `QdrantStore.upsert()`: batch insert 500 points per request (Qdrant recommended batch size).

**Verification:**
```bash
# Start worker
celery -A src.infrastructure.message_queue.celery_app worker -Q ingestion.documents -l info
# Upload a PDF via API
# Watch worker logs — should see status transitions
# Check Qdrant dashboard — verify vectors appear in tenant collection
# Check DB job status = COMPLETED
```

---

### MODULE 3 — RAG Query Pipeline (Days 14–20)

---

#### DAY 14 — Embedding Service + Dense Retriever

**Dependencies:** Module 2 complete, Qdrant has test data.

**Files to create:**
- `src/services/retrieval/retrievers/base.py` — IRetriever ABC
- `src/services/retrieval/retrievers/dense_retriever.py`
  - `search(query, tenant_id, collection_ids, filters, top_k)` → List[RetrievedChunk]
  - Qdrant Filter builder from metadata dict
- `src/services/retrieval/filters/metadata_filter.py` — Qdrant Filter construction
- `src/domain/value_objects/chunk.py` — add RetrievedChunk dataclass

**Key implementation notes:**
- `DenseRetriever.search()`: embed query → Qdrant ANN search with payload filter.
- Always filter by `tenant_id` in Qdrant query — this is the isolation guarantee.
- `RetrievedChunk`: `{text, score, document_id, collection_id, page_num, source_filename, chunk_index, metadata}`.
- `similarity_threshold` filter: drop results with score < threshold (from tenant config).

**Verification:**
```bash
python -c "
from src.services.retrieval.retrievers.dense_retriever import DenseRetriever
import asyncio
results = asyncio.run(DenseRetriever().search(
    query='indemnification clause',
    tenant_id='tenant1',
    collection_ids=None,
    filters={},
    top_k=5
))
for r in results:
    print(r.score, r.text[:100])
"
```

---

#### DAY 15 — Sparse Retriever + Ensemble (RRF)

**Dependencies:** Day 14 complete, Qdrant sparse vectors enabled.

**Files to create:**
- `src/services/retrieval/retrievers/sparse_retriever.py` — BM25 via Qdrant sparse vectors
- `src/services/retrieval/retrievers/ensemble_retriever.py` — RRF combiner

**Key implementation notes:**
- RRF formula: `score(doc) = Σ 1/(rank_i + 60)` across all retrievers and query variants.
- RRF constant `60` is standard — prevents top-ranked docs from dominating too heavily.
- Ensemble: deduplicate by `chunk_id` before RRF (same chunk may appear in dense and sparse results).
- `hybrid_alpha` from tenant config: if 1.0, only dense scores. If 0.0, only sparse. Values between = weighted RRF.

**Verification:**
```bash
python -c "
from src.services.retrieval.retrievers.ensemble_retriever import EnsembleRetriever
import asyncio
results = asyncio.run(EnsembleRetriever().search(
    query='indemnification',
    tenant_id='tenant1',
    collection_ids=None,
    filters={},
    top_k=10,
    hybrid_alpha=0.6
))
print(f'Got {len(results)} results')
for r in results[:3]:
    print(r.score, r.text[:80])
"
```

---

#### DAY 16 — Query Rewriter + Reranker

**Dependencies:** Day 15, LangSmith prompt created for multi-query.

**Files to create:**
- `src/services/retrieval/filters/query_rewriter.py`
  - `multi_query_expand(query, n=3)` → List[str] via LLM
  - `hyde_expand(query)` → hypothetical answer embedding
- `src/services/retrieval/rerankers/base.py` — IReranker ABC
- `src/services/retrieval/rerankers/cohere_reranker.py`
- `src/services/retrieval/rerankers/cross_encoder_reranker.py` — local fallback

**Key implementation notes:**
- `multi_query_expand`: lightweight LLM call (GPT-4o-mini is fine). Prompt from LangSmith Hub.
- HyDE: embed the hypothetical answer instead of the raw query. Better semantic match.
- Cohere reranker: cross-encoder score is much more accurate than vector similarity.
- Local fallback: `cross-encoder/ms-marco-MiniLM-L-6-v2` from HuggingFace for offline/cost-sensitive tenants.
- Reranker always reduces to `top_k` from tenant config (e.g., 20 → 5).

**Verification:**
```bash
python -c "
from src.services.retrieval.filters.query_rewriter import QueryRewriter
import asyncio
variants = asyncio.run(QueryRewriter().expand('indemnification clauses Q3', n=3))
print(variants)  # Should be 3 semantic variants
"
```

---

#### DAY 17 — LLM Service + Prompt Manager + Response Cache

**Dependencies:** Day 16, LangSmith Hub prompts created.

**Files to create:**
- `src/services/llm/providers/base.py` — ILLM ABC (generate, stream, count_tokens)
- `src/services/llm/providers/openai_provider.py` — async stream + non-stream
- `src/services/llm/providers/anthropic_provider.py`
- `src/services/llm/providers/factory.py` — LLMProviderFactory
- `src/services/llm/prompt_manager.py` — load from LangSmith Hub with version pinning
- `src/services/llm/response_cache.py` — Redis semantic cache
- `src/services/llm/llm_service.py` — orchestrates cache + trace + call
- `src/infrastructure/observability/langsmith_client.py`

**Key implementation notes:**
- `PromptManager.load(prompt_id, version)`: loads from LangSmith Hub. Cache result in memory for 10 minutes (avoid Hub API on every request).
- `ResponseCache`: key = `sha256(f"{tenant_id}:{normalize_query(message)}")`. Normalize = lowercase + remove punctuation + sort words for near-duplicate detection.
- `LLMService.generate()` with LangSmith tracing: wrap in `RunTree` — parent run = full query, child runs = retrieval + LLM call.
- `LLMService` selects provider from tenant config: `LLMProviderFactory.get(config.llm_provider)`.
- Token budget enforcement: if messages exceed model context, trim oldest STM turns first.

**Verification:**
```bash
python -c "
from src.services.llm.llm_service import LLMService
import asyncio
svc = LLMService()
resp = asyncio.run(svc.generate(
    messages=[{'role':'user','content':'What is 2+2?'}],
    config={'provider':'openai','model':'gpt-4o-mini','temperature':0,'max_tokens':50},
    tenant_id='t1'
))
print(resp.content)
# Check LangSmith dashboard — run should appear
"
```

---

#### DAY 18 — Session Service + Memory (STM + LTM)

**Dependencies:** Day 17 complete.

**Files to create:**
- `src/infrastructure/repositories/session_repository.py`
- `src/infrastructure/repositories/message_repository.py`
- `src/services/session/session_service.py`
  - `create_session(user_id, tenant_id)` → snapshot config at creation
  - `get_session(session_id)` → validate + return
  - `end_session(session_id)`
  - `increment_turn(session_id)`
- `src/services/memory/short_term/redis_stm.py`
  - `get_history(session_id, n)` → last N turns
  - `add_turn(session_id, role, content)`
  - `clear(session_id)`
- `src/services/memory/long_term/qdrant_ltm.py`
  - `search_memories(user_id, tenant_id, query)` → relevant past memories
  - `store_memory(user_id, tenant_id, summary)`
- `src/services/memory/long_term/ltm_service.py`
  - `summarize_and_store(session_id, user_id, tenant_id)` — LLM summarization
- `src/services/memory/memory_service.py` — unified interface
- `src/workers/ltm_worker.py` — Celery task for async LTM
- `src/api/v1/routers/sessions.py`
- `src/api/v1/schemas/session.py`

**Key implementation notes:**
- STM in Redis: `lpush stm:{session_id}` + `ltrim` to window size. TTL = 7 days sliding (reset on each message).
- STM format per entry: `{"role": "user", "content": "...", "ts": 1234567890}`.
- Session `config_snapshot` = `tenant_configs.config` at creation time (JSON copy). This ensures config changes don't affect in-progress sessions.
- LTM Qdrant collection: `ltm_{tenant_id}`. Filtered by `user_id` on retrieval.
- LTM summarization prompt: extract user preferences, key facts, topics, tone preferences.

**Verification:**
```bash
# Create session via API
curl -X POST localhost:8000/v1/sessions \
  -H "Authorization: Bearer <token>"
# Check Redis: stm:{session_id} key exists
# Send a few messages, check STM grows
# After 20 turns, check LTM summarization task queued in Celery
```

---

#### DAY 19 — Retrieval Service (Full Orchestration)

**Dependencies:** Days 14-18 complete.

**Files to create:**
- `src/services/retrieval/retrieval_service.py` — orchestrates the full retrieval pipeline

**Key implementation notes:**
- `RetrievalService.retrieve(query, session_id, collection_ids, filters, config)`:
  1. If `config.hyde_enabled`: run HyDE in parallel with original query
  2. If `config.multi_query_enabled`: expand to N variants
  3. For each variant: run dense + sparse retrieval
  4. RRF merge across all variants and retriever types
  5. If `config.reranker_enabled`: rerank top 20 → top_k
  6. Filter by `similarity_threshold`
  7. Return `List[RetrievedChunk]` with scores
- All sub-tasks (dense, sparse, HyDE, multi-query) run as `asyncio.gather()` where possible.
- Prometheus: `rag_retrieval_duration_seconds`, `rag_chunks_returned`.

**Verification:**
```bash
python -c "
from src.services.retrieval.retrieval_service import RetrievalService
import asyncio

config = {
  'top_k': 5, 'similarity_threshold': 0.6,
  'hybrid_alpha': 0.6, 'reranker_enabled': True,
  'hyde_enabled': True, 'multi_query_enabled': True
}
chunks = asyncio.run(RetrievalService().retrieve(
    query='contract penalty clause',
    tenant_id='tenant1',
    session_id='sess1',
    collection_ids=None,
    filters={},
    config=config
))
print(f'Retrieved {len(chunks)} chunks')
"
```

---

#### DAY 20 — Guardrails Service

**Dependencies:** Day 17 complete (LLM service needed for topic classifier).

**Files to create:**
- `src/services/guardrails/input/base.py` — IInputGuardrail ABC
- `src/services/guardrails/input/pii_detector.py` — Presidio AnalyzerEngine
- `src/services/guardrails/input/toxicity_filter.py` — OpenAI Moderation API
- `src/services/guardrails/input/prompt_injection.py` — heuristic patterns + classifier
- `src/services/guardrails/input/topic_classifier.py` — LLM-based with allowed_topics
- `src/services/guardrails/output/base.py` — IOutputGuardrail ABC
- `src/services/guardrails/output/hallucination_check.py` — NLI cross-encoder
- `src/services/guardrails/output/pii_scrubber.py` — Presidio AnonymizerEngine
- `src/services/guardrails/output/citation_validator.py`
- `src/services/guardrails/guardrail_service.py` — runs enabled guardrails from config

**Key implementation notes:**
- `GuardrailService.check_input(message, config)`: runs enabled input guardrails as `asyncio.gather()`. Returns `GuardrailResult(passed, action, masked_message, flags)`.
- `pii_action` from config: `"mask"` → replace with `[PII_MASKED]`. `"reject"` → raise `InputRejectedError`. `"allow"` → pass through.
- Hallucination check: `cross-encoder/nli-deberta-v3-base` scores (answer, context) for entailment. Score < threshold → append disclaimer.
- Prometheus: `rag_guardrail_blocks_total{type, action, tenant_id}`.

**Verification:**
```bash
python -c "
from src.services.guardrails.guardrail_service import GuardrailService
import asyncio
config = {'guardrails': {'input': {'pii_detection': True, 'pii_action': 'mask', 'toxicity_filter': True}}}
result = asyncio.run(GuardrailService().check_input(
    'My SSN is 123-45-6789, help me with contracts',
    config
))
print(result.masked_message)  # SSN should be masked
"
```

---

### MODULE 4 — Chat Service + WebSocket (Days 21–24)

---

#### DAY 21 — Chat Service (Full RAG Pipeline)

**Dependencies:** Days 14-20 complete.

**Files to create:**
- `src/services/chat/chat_service.py` — THE main orchestrator

**Key implementation notes:**
- `ChatService.query(request, session, config)` pipeline (in order):
  1. Input guardrails (parallel async)
  2. Load STM + LTM (parallel async)
  3. Query rewriting (if enabled)
  4. Ensemble retrieval
  5. Cache check
  6. Prompt construction (system + history + LTM context + RAG context + query)
  7. LLM call (stream or full)
  8. Output guardrails
  9. Cache write + STM update + LTM enqueue check
  10. Persist message to PostgreSQL
  11. Return `ChatResponse`
- Token budget: count tokens of full prompt. If over model limit, trim STM history from oldest first (never trim RAG context or system prompt).
- `ChatResponse`: `{session_id, message_id, content, sources, usage, cached, turn_count}`.

**Verification:**
```bash
python -c "
from src.services.chat.chat_service import ChatService
# Full pipeline test with all mocked externals
import asyncio
# See tests/unit/services/test_chat_service.py
"
```

---

#### DAY 22 — REST Chat API + WebSocket Handler

**Dependencies:** Day 21 complete.

**Files to create:**
- `src/api/v1/schemas/chat.py` — ChatRequest, ChatResponse, MessageSchema
- `src/api/v1/routers/chat.py` — POST /v1/chat/completions
- `src/api/v1/routers/websocket.py` — WS /v1/ws/chat/{session_id}

**Key implementation notes:**
- REST endpoint: delegates to `ChatService.query()`. Await full response, return JSON.
- WebSocket: `FastAPI WebSocket` with proper lifecycle:
  - `websocket.accept()`
  - validate JWT from query param `?token=<jwt>` (browsers can't set headers on WS)
  - loop: receive message → call `ChatService.query(stream=True)` → send tokens as they arrive
  - handle `WebSocketDisconnect` gracefully
- WebSocket message protocol (JSON throughout):
  - Client sends: `{"message": "...", "collection_ids": [], "filters": {}}`
  - Server sends tokens: `{"type": "token", "content": "..."}`
  - Server sends final: `{"type": "done", "sources": [...], "usage": {...}, "session_id": "..."}`
  - Server sends error: `{"type": "error", "code": "...", "message": "..."}`

**Verification:**
```bash
# Test REST
curl -X POST localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer <token>" \
  -d '{"message": "What are the key clauses?", "session_id": null}'

# Test WebSocket (use wscat or a test script)
wscat -c "ws://localhost:8000/v1/ws/chat/new?token=<jwt>"
```

---

#### DAY 23 — v2 SSE Streaming + API Router Wiring

**Dependencies:** Day 22 complete.

**Files to create:**
- `src/api/v2/routers/chat.py` — SSE streaming via `StreamingResponse`
- `src/api/v2/router.py`
- `src/api/main.py` — mount both v1 and v2 routers, finalize middleware stack

**Key implementation notes:**
- SSE response: `StreamingResponse(generator(), media_type="text/event-stream")`.
- SSE format: `data: {"type": "token", "content": "..."}\n\n`
- v2 adds `X-Session-ID` response header so client can track session without parsing body.
- Middleware registration order (outermost first): CORSMiddleware → RequestIDMiddleware → TenantContextMiddleware → RateLimitMiddleware. Auth happens at dependency level (not middleware) for per-route flexibility.

**Verification:**
```bash
curl -N -H "Authorization: Bearer <token>" \
  "localhost:8000/v2/chat/stream?message=Hello&session_id=new"
# Should see SSE token events streamed
```

---

#### DAY 24 — Integration Test: Full End-to-End

**Dependencies:** Days 1-23 complete. testcontainers installed.

**Files to create:**
- `tests/conftest.py` — pytest fixtures: test DB, Redis, Qdrant, RMQ via testcontainers
- `tests/integration/test_auth_flow.py`
- `tests/integration/test_ingestion_api.py` — upload → process → verify in Qdrant
- `tests/integration/test_chat_api.py` — query → retrieve → generate → return
- `tests/integration/test_websocket.py` — WS session lifecycle

**Key implementation notes:**
- testcontainers: spin up real Postgres, Redis, Qdrant Docker containers per test session.
- `tests/conftest.py`: `async_session` fixture, `test_tenant` fixture, `test_user` fixture.
- Integration tests test the HTTP API — they don't call services directly.
- Ingestion test: must mock Celery (use `task_always_eager=True` in test config) so worker runs synchronously.

**Verification:**
```bash
make test            # pytest tests/integration/ -v
# All tests pass
# Coverage report: pytest --cov=src --cov-report=html
```

---

### MODULE 5 — Observability (Days 25–27)

---

#### DAY 25 — Prometheus Metrics

**Dependencies:** Any module, infra running.

**Files to create:**
- `src/infrastructure/observability/prometheus_metrics.py`
  - `rag_ingestion_duration_seconds` — histogram per doc_type, tenant
  - `rag_ingestion_chunk_count` — gauge per tenant
  - `rag_query_duration_seconds` — histogram per tenant
  - `rag_retrieval_score` — histogram of relevance scores
  - `rag_llm_tokens_total` — counter per provider, model, tenant
  - `rag_llm_latency_seconds` — histogram per provider, model
  - `rag_cache_hits_total` — counter per tenant
  - `rag_guardrail_blocks_total` — counter per type, action, tenant
  - `rag_active_sessions` — gauge per tenant
  - `rag_ingestion_jobs_total` — counter per status, tenant
- Instrument `chat_service.py`, `retrieval_service.py`, `llm_service.py`, `ingestion_worker.py`

**Verification:**
```bash
curl localhost:8000/metrics | grep rag_
# Should see all custom metrics
```

---

#### DAY 26 — Grafana Dashboards

**Dependencies:** Day 25, Prometheus scraping.

**Files to create:**
- `infra/grafana/dashboards/api_overview.json` — request rate, latency p50/p95/p99, error rate
- `infra/grafana/dashboards/rag_pipeline.json` — retrieval latency, rerank scores, cache hit rate
- `infra/grafana/dashboards/llm_costs.json` — tokens per tenant, estimated cost, provider breakdown
- `infra/grafana/dashboards/celery_workers.json` — queue depth, task duration, failure rate
- `infra/grafana/provisioning/dashboards.yml`
- `infra/grafana/provisioning/datasources.yml`

**Verification:**
```bash
# Open localhost:3000 (Grafana)
# All 4 dashboards auto-provisioned
# Run some queries — see metrics update in real time
```

---

#### DAY 27 — Logging + Structured Tracing

**Dependencies:** Any module.

**Files to create:**
- `src/core/logging.py` — structlog JSON config
- `src/infrastructure/observability/tracing.py` — request context propagation

**Key implementation notes:**
- Every log line includes: `request_id`, `tenant_id`, `user_id`, `session_id` (from ContextVars).
- Use structlog `BoundLogger` — bind context once at middleware level, all subsequent logs carry it.
- Log levels: DEBUG (dev), INFO (prod default). Sensitive fields (JWT, passwords) excluded.
- Celery workers: bind `job_id`, `tenant_id` at task start for all task-level logs.

**Verification:**
```bash
make dev
# Make a chat request
# Check logs: each line should be JSON with request_id, tenant_id
```

---

### MODULE 6 — Production Hardening (Days 28–32)

---

#### DAY 28 — Nginx + Security Headers

**Files to create:**
- `infra/nginx/nginx.conf` — TLS termination, gzip, WebSocket upgrade, security headers
- `docker/nginx/Dockerfile`

**Key configuration:**
```nginx
# WebSocket upgrade
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";

# Security headers
add_header X-Content-Type-Options nosniff;
add_header X-Frame-Options DENY;
add_header X-XSS-Protection "1; mode=block";
add_header Strict-Transport-Security "max-age=31536000" always;

# Rate limiting at Nginx level (coarse) — fine-grained in Redis
limit_req_zone $binary_remote_addr zone=api:10m rate=100r/m;
```

---

#### DAY 29 — Docker Multi-Stage Builds + docker-compose production

**Files to create:**
- `docker/api/Dockerfile` — multi-stage: builder (install deps) + runtime (copy only needed files)
- `docker/worker/Dockerfile`
- `infra/docker-compose.yml` — update with health checks, restart policies, resource limits

**Key implementation notes:**
- API Dockerfile: `python:3.12-slim` base. Multi-stage to avoid build tools in final image.
- Worker Dockerfile: may need `tesseract-ocr`, `ffmpeg` installed at OS level.
- `docker-compose.yml` healthchecks: postgres (`pg_isready`), redis (`redis-cli ping`), qdrant (`curl /health`).
- Resource limits: API `mem_limit: 512m`, Worker `mem_limit: 2g` (OCR is memory-intensive).

---

#### DAY 30 — Pre-commit Hooks + CI Pipeline

**Files to create:**
- `.pre-commit-config.yaml` — ruff (lint+format), mypy (strict), bandit (security), detect-secrets
- `.github/workflows/ci.yml`
  - Lint (ruff, mypy)
  - Unit tests (pytest tests/unit/)
  - Integration tests (pytest tests/integration/ with docker-compose)
  - Security scan (bandit, safety)
  - LangSmith golden dataset eval (fail if recall@5 < 0.85)

**Verification:**
```bash
pre-commit install
pre-commit run --all-files  # All hooks pass
```

---

#### DAY 31 — Cleanup Worker + Webhook Notifications

**Files to create:**
- `src/workers/cleanup_worker.py`
  - `cleanup_expired_jobs()` — delete jobs older than 30 days
  - `cleanup_orphaned_s3_files()` — S3 objects with no DB document row
  - `cleanup_expired_sessions()` — mark sessions inactive > 30 days as expired
- Webhook notifications in `ingestion_service.py` — POST to `tenant.webhook_url` on COMPLETED/FAILED

---

#### DAY 32 — Final Integration + Load Test

**Files to create:**
- `scripts/benchmark_retrieval.py` — recall@5 against golden datasets
- `tests/golden_datasets/qa_pairs_sample.jsonl` — 50 QA pairs

**Load test (using locust or k6):**
- 100 concurrent users
- Mix: 70% chat queries, 20% ingestion, 10% status polling
- Target: p99 chat < 2s, p99 ingestion acceptance < 500ms
- Run for 10 minutes, verify no memory leaks, no Redis exhaustion

---

## 9. Environment Variables Reference

```bash
# Application
APP_ENV=development          # development | production
APP_SECRET_KEY=              # JWT signing key (RS256 private key PEM)
APP_PUBLIC_KEY=              # JWT verification key (RS256 public key PEM)
APP_CORS_ORIGINS=http://localhost:3000

# PostgreSQL
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=ragbot
POSTGRES_USER=ragbot
POSTGRES_PASSWORD=
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# RabbitMQ
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest
RABBITMQ_VHOST=/

# Celery
CELERY_BROKER_URL=amqp://guest:guest@localhost:5672//
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_API_KEY=             # for Qdrant Cloud

# AWS S3
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=us-east-1
S3_BUCKET_NAME=ragbot-files
S3_PRESIGNED_URL_TTL=3600

# OpenAI
OPENAI_API_KEY=
OPENAI_EMBEDDING_MODEL=text-embedding-3-large
OPENAI_DEFAULT_MODEL=gpt-4o

# Anthropic
ANTHROPIC_API_KEY=

# Cohere (reranking)
COHERE_API_KEY=

# LangSmith
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=ragbot-production
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com

# Prometheus
PROMETHEUS_ENABLED=true

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json              # json | text (text for local dev)
```

---

## 10. Testing Strategy

### Unit Tests (no I/O)
- Pure logic: chunkers, enrichers, parsers (with mocked file I/O), guardrail rules, RRF scoring
- Use `pytest` with `pytest-asyncio`
- Mock all external calls (OpenAI, Cohere, S3, Qdrant) with `unittest.mock.AsyncMock`

### Integration Tests (real infrastructure via testcontainers)
- Real PostgreSQL, Redis, Qdrant, RabbitMQ via testcontainers
- Mock only external APIs (OpenAI, Cohere, AWS S3 via LocalStack)
- Test full request lifecycle: HTTP request → middleware → service → DB → response

### End-to-End Tests
- `tests/e2e/test_full_rag_pipeline.py`: upload PDF → wait for indexing → query → verify answer contains expected content
- Run against a full docker-compose stack

### LangSmith Evaluation (CI gate)
- `tests/golden_datasets/qa_pairs_sample.jsonl`: 50 QA pairs per tenant type
- Format: `{"input": "query", "expected_sources": ["doc_id"], "expected_answer_contains": ["keyword"]}`
- CI evaluates recall@5 (did expected source appear in top 5 retrieved chunks?) — fail build if < 0.85

---

## Quick Reference: Dependency Chain

```
Day 1  (infra skeleton)
  └── Day 2  (DB models + migrations)
        └── Day 3  (auth + RBAC)
              └── Day 4  (Redis + rate limiting + collections)
                    └── Day 5  (S3 + Qdrant + Celery)
                          └── Day 6  (ingestion API + job tracking)
                                ├── Day 7  (PDF digital parser)
                                │     └── Day 8  (OCR + mixed PDF)
                                │           └── Day 9  (image + VLM)
                                ├── Day 10 (CSV + Excel)
                                ├── Day 11 (audio + video)
                                └── Day 12 (factory + chunkers + enrichers)
                                      └── Day 13 (Celery worker — full pipeline)
                                            └── Day 14 (dense retriever)
                                                  └── Day 15 (sparse + ensemble)
                                                        └── Day 16 (query rewriter + reranker)
                                                              └── Day 17 (LLM service + cache)
                                                                    └── Day 18 (session + memory)
                                                                          └── Day 19 (retrieval service)
                                                                                └── Day 20 (guardrails)
                                                                                      └── Day 21 (chat service)
                                                                                            └── Day 22 (REST + WS API)
                                                                                                  └── Day 23 (v2 SSE)
                                                                                                        └── Day 24 (integration tests)
                                                                                                              ├── Day 25-27 (observability)
                                                                                                              └── Day 28-32 (production hardening)
```

---

*Last updated: 2026-04-02*  
*Total estimated duration: 32 focused working days (~6-8 weeks at 5 days/week)*
