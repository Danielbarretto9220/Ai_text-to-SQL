# AI-Powered Banking Metadata Repository

## Project Overview

This repository contains a banking loan database developed in PostgreSQL along with a complete metadata layer for AI-powered Text-to-SQL systems.

The project includes:

- Banking relational database
- Dummy banking dataset
- Metadata schema
- Business glossary
- Table metadata
- Column metadata
- Relationship metadata
- Sample values
- Business synonyms

---

## Database Tables

- branches
- customers
- loan_officers
- loans
- emi_payments

---

## Metadata Components

- meta.tables
- meta.columns
- meta.relationships
- meta.business_glossary
- meta.query_patterns
- meta.document_embeddings
- meta.change_log
- meta.prompt_versions
- meta.business_rules

---

## Technologies

- PostgreSQL
- pgvector (PostgreSQL extension, for vector embeddings)
- SQLAlchemy (ORM layer over meta.*)
- Python 3.x
- pgAdmin 4
- SQL
- VS Code
- Git
- GitHub

---

## Project Structure

The repo is laid out to match the target architecture in [`enterprise-text-to-sql-architecture.md`](enterprise-text-to-sql-architecture.md) — see [`docs/MODULES.md`](docs/MODULES.md) for the full build-out checklist and status of every module.

```
├── METADATA/                  meta schema + population SQL (implemented)
├── SQL/                       banking warehouse schema + dummy data (implemented)
├── app/
│   ├── db/                    connection handling + metadata reads + SQLAlchemy ORM models (implemented)
│   ├── retrieval/             document builder, vector search, hybrid search (RRF), cross-encoder
│   │                          reranking, relationship-graph join paths, confidence scoring (implemented)
│   ├── prompting/              prompt_builder.py + templates/user_prompt.txt (implemented)
│   ├── validation/            sql_parser.py (sqlglot), guardrails.py (LIMIT/complexity/business rules),
│   │                          cost_estimator.py (EXPLAIN) (implemented)
│   ├── llm/                   client.py (Groq via the openai SDK) + schemas.py (implemented)
│   ├── api/                   routes_query.py (/query, /execute), routes_feedback.py (/feedback),
│   │                          routes_admin.py (/health, /metrics, /schema/search, /admin/reindex),
│   │                          deps.py (DB dependency), schemas.py (Pydantic request/response models),
│   │                          metrics.py (Prometheus counters/histogram) (implemented)
│   ├── pipeline.py            end-to-end orchestrator: retrieval → prompt → LLM → validate →
│   │                          (opt-in) execute (implemented)
│   └── main.py                FastAPI entrypoint — loads embedding/reranker models once at startup via
│                               lifespan (implemented); config.py extended with API_HOST/API_PORT,
│                               EXECUTE_ENABLED (default off) + row cap/timeout, LOG_LEVEL (implemented)
├── ui/
│   └── streamlit_app.py       Streamlit UI — calls the FastAPI service over HTTP, not app.pipeline
│                               directly (implemented)
├── workers/
│   ├── reindex_embeddings.py  embedding indexing job (implemented, full-rebuild only)
│   ├── generate_docs.py       auto-doc generation from information_schema (implemented)
│   ├── drift_detector.py      DDL drift → re-embed trigger (implemented)
│   ├── sync_data_content.py   row_count_estimate + sample_values refresh from live data (implemented)
│   └── scheduler.py           runs sync_data_content on an interval (implemented)
├── tests/                     pytest suite — validation/db/retrieval/prompting (fast, no LLM) +
│                               llm/pipeline/api/e2e (live, real Groq calls) (implemented)
├── test_connection.py         standalone DB connectivity check (implemented)
└── docs/
    ├── MODULES.md              module-by-module build status
    ├── API_AND_TESTING_PLAN.md the plan the API layer + test suite were built from
    └── schema/                 auto-generated per-table Markdown docs (generated, not hand-edited)
```

## Prerequisites & Setup

- **PostgreSQL server**, with the **pgvector** extension enabled (used for storing/querying embeddings via the `vector` type and `<=>` distance operator)
- **Python 3.x** and **pip**
- Python packages: `pip install -r requirements.txt` (pinned versions — `psycopg2-binary`, `python-dotenv`,
  `sentence-transformers`, `sqlalchemy`, `pgvector`, `apscheduler`, `openai`, `pydantic`, `sqlglot`,
  `fastapi`, `uvicorn`, `streamlit`, `pytest`, `httpx`, `prometheus-client`, `requests`)
  - `sentence-transformers` generates embeddings locally (`all-MiniLM-L6-v2`) and drives the reranker
    (`cross-encoder/ms-marco-MiniLM-L-6-v2`); pulls in `torch`/`transformers`
  - `pgvector` is the Python package (not the Postgres extension) — provides `pgvector.sqlalchemy.Vector`
  - `apscheduler` drives `workers/scheduler.py`'s interval-based auto-sync trigger
  - `openai` is the SDK `app/llm/client.py` uses to talk to Groq — Groq documents its API as an
    OpenAI-compatible drop-in, so the client just points the `openai` SDK at
    `https://api.groq.com/openai/v1`; defaults to `openai/gpt-oss-20b`, escalating to
    `openai/gpt-oss-120b` only on a repair retry; `pydantic` backs `app/llm/schemas.py`'s
    structured-output models
  - `fastapi` + `uvicorn` serve the HTTP API (`app/main.py`); `streamlit` + `requests` drive the UI
    (`ui/streamlit_app.py`); `prometheus-client` backs `/metrics`; `pytest` + `httpx` (the latter required
    by FastAPI's `TestClient`) run the test suite
- **Internet access on first run**, to download the `all-MiniLM-L6-v2` embedding model and the
  `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker model from Hugging Face Hub, and to call the Groq API
- A **`.env` file** in the project root (not included in the repo) defining:
  ```
  DB_HOST=localhost
  DB_PORT=5432
  DB_NAME=your_db_name
  DB_USER=your_db_user
  DB_PASSWORD=your_db_password
  GROQ_API_KEY=your_groq_api_key
  GROQ_MODEL=openai/gpt-oss-20b
  GROQ_ESCALATION_MODEL=openai/gpt-oss-120b
  API_HOST=127.0.0.1
  API_PORT=8000
  API_BASE_URL=http://127.0.0.1:8000
  EXECUTE_ENABLED=false
  EXECUTE_ROW_CAP=1000
  EXECUTE_STATEMENT_TIMEOUT_MS=5000
  LOG_LEVEL=INFO
  ```
  `GROQ_API_KEY` is from [console.groq.com/keys](https://console.groq.com/keys) — free, no billing
  required, unlike Gemini/xAI/Anthropic which this project tried first (see CLAUDE.md's "Live-test rate
  limits" section for that history). `GROQ_MODEL` and `GROQ_ESCALATION_MODEL` are both optional (default
  to `openai/gpt-oss-20b` and `openai/gpt-oss-120b`) — every `call_llm()` attempt starts on the smaller
  model, and only its one repair retry escalates to the larger one. `EXECUTE_ENABLED` gates
  `app/pipeline.py`'s `execute_query()` — the only code path that runs LLM-generated SQL against the real
  database — and defaults to **false**; the rest have working defaults and only need overriding if you
  want different values.

There's no `pyproject.toml`/packaging yet, so run modules from the repo root with `-m` so `app`/`workers`/`tests` resolve as packages, e.g. `python -m workers.reindex_embeddings`.

### Running the API, UI, and tests

On Windows, `.\start.ps1` starts both the API and the UI in their own windows, waiting for the API's
`/health` check to pass before launching the UI (so the UI isn't racing the API's ~10-20s startup model
load). Run manually instead if you want more control:

```
uvicorn app.main:app --reload             # FastAPI service at http://127.0.0.1:8000 (Swagger UI at /docs)
streamlit run ui/streamlit_app.py         # Streamlit UI at http://localhost:8501 (needs the API running)
pytest                                    # full suite — see the GROQ_API_KEY note above; live tests are free-tier rate-limited
pytest -m "not live"                      # fast subset, no Groq calls (safe to run anytime)
```

---

## Current Progress

✔ Database Schema Created

✔ Dummy Dataset Populated

✔ Metadata Schema Created

✔ Table Metadata

✔ Column Metadata

✔ Relationship Metadata

✔ Business Glossary

✔ Vector Embeddings (pgvector)

✔ Business Descriptions (table & column level)

✔ Business Synonyms (column level)

✔ Sample Values (column level)

✔ Query Pattern Metadata (few-shot SQL example bank)

✔ Change Log (audit trail on meta.tables/meta.columns changes)

✔ Prompt Versioning (meta.prompt_versions)

✔ Business Rules (meta.business_rules — guardrail definitions for SQL validation)

✔ ORM/Typed Models (SQLAlchemy models over meta.*, app/db/models.py)

✔ Auto-Generated Schema Docs (docs/schema/*.md from information_schema + meta.*)

✔ Automatic Metadata Refresh (workers/drift_detector.py — DDL drift → sync meta.* → regenerate docs → incremental re-embed)

✔ Data-Content Auto-Sync (workers/sync_data_content.py — refreshes row_count_estimate and sample_values from live data, no DDL required; workers/scheduler.py runs it on an interval)

✔ Retrieval Layer (app/retrieval/hybrid_search.py — BM25 + vector search via Reciprocal Rank Fusion; rerank.py — cross-encoder reranking; relationship_graph.py — BFS join-path resolution over meta.relationships; confidence.py — retrieve_context() pipeline entry point with confidence scoring + ambiguity-clarification path)

✔ Prompting (app/prompting/prompt_builder.py — reads the already-seeded system prompt from meta.prompt_versions, assembles CONTEXT from retrieve_context() plus two extra hybrid_search() calls for business_terms/query_patterns, and renders the final user prompt via app/prompting/templates/user_prompt.txt)

✔ LLM Client (app/llm/client.py — Groq via the openai SDK pointed at Groq's OpenAI-compatible endpoint; app/llm/schemas.py — a single Pydantic SQLGenerationResponse covering both the normal SQL-response and insufficient_context escape-hatch branches of the seeded system prompt. Originally built against Gemini and live-verified there (a lookup question, an aggregation question the retrieval layer flagged low-confidence for, and an out-of-scope question correctly triggering insufficient_context); tried xAI Grok, then Anthropic Claude (both require paid billing), then switched to Groq on 2026-08-21 — the one genuinely free-tier provider tried. Uses response_format={"type": "json_object"}, not Groq's json_schema strict mode, after live-testing found Groq's strict-mode validator rejects correct model output for this schema's nullable fields (see CLAUDE.md's "LLM client" section for the repro). Live-verified: both test_llm.py cases pass against real Groq calls)

✔ SQL Generation & Validation (app/validation/sql_parser.py — sqlglot-based syntax/read-only/hallucination/join checks; guardrails.py — LIMIT injection, complexity limits, and a defensive per-rule_type business rules engine over meta.business_rules' genuinely heterogeneous rule_logic shapes; cost_estimator.py — EXPLAIN-based cost/row thresholds. app/pipeline.py ties it all together as generate_validated_sql() — retrieval → prompt → LLM → validate → one repair-retry on validation failure — plus an opt-in execute_query() with real safety rails (read-only transaction, statement timeout, row cap, always rolled back). Live-verified end to end including the repair-retry path and execute_query()'s defense in depth: a direct UPDATE attempt bypassing all validation was rejected by Postgres's own READ ONLY transaction, not just the Python guardrails. Bug found and fixed post-Groq-migration: check_hallucinations() had no concept of SELECT-list aliases, so a valid ORDER BY <alias> referencing a COUNT(...) AS <alias> from the SELECT list was flagged as an unknown column; a user-reported real Groq query surfaced it. Fixed by exempting unqualified column refs that match a known SELECT-list alias, with a regression test)

✔ API & App (app/main.py — FastAPI service loading the embedding/reranker models once at startup via `lifespan`; app/api/routes_query.py, routes_feedback.py, routes_admin.py — all 7 endpoints from the architecture doc's §6.4, including `POST /api/v1/execute` which always re-validates a query server-side before running it, and `GET /api/v1/health` which never makes a live LLM call so polling doesn't burn free-tier rate-limit quota; app/api/schemas.py, deps.py, metrics.py; ui/streamlit_app.py — a Streamlit client that talks to the API over HTTP, never importing the pipeline directly, with a dedicated "Run this SQL on the database" button (POST /api/v1/execute) decoupled from generation so execution is always an explicit, separate choice. METADATA/20_add_query_log_and_feedback.sql adds meta.query_log/meta.query_feedback, closing the feedback-loop-into-the-few-shot-bank design from the architecture doc's §10. Manually verified end to end under the Gemini integration originally (all 7 endpoints via curl/Swagger, the Streamlit UI driven in a real browser session, a transient live-LLM 503 confirmed to surface cleanly without corrupting logged state), and re-verified under Groq: health, a direct POST /api/v1/query via curl, and the Streamlit UI driven in a real browser session (question → spinner → SQL/confidence display) all confirmed working against real Groq calls; demo query_log rows cleaned up afterward. The transient-error-mid-session check hasn't been separately re-triggered under Groq)

✔ Test Suite (pytest.ini + tests/conftest.py — session-scoped model/DB fixtures, a TestClient wired to a test-controlled DB connection via `app.dependency_overrides`, and retry helpers for transient `openai.InternalServerError`, deliberately not `openai.RateLimitError` — a distinction learned from Gemini's quota errors looking superficially retryable. tests/test_validation.py, test_db.py, test_retrieval.py, test_prompting.py — 56 tests (+1 for the check_hallucinations() alias regression), no LLM calls, all green. tests/test_llm.py, test_pipeline.py, test_api.py, test_e2e.py — 13 `live`-marked tests covering the full generation → validation → execution → feedback journey; live-run against real Groq: test_llm.py's 2 tests and test_pipeline.py's 7 tests all pass (initially 6/7 — the one failure was the check_hallucinations() alias bug, since fixed, not a model-quality issue). test_api.py/test_e2e.py's live HTTP-layer tests haven't been separately re-run against Groq via pytest yet, though the equivalent request path was exercised manually)

---

## Next Steps

Everything in [`docs/API_AND_TESTING_PLAN.md`](docs/API_AND_TESTING_PLAN.md) is built. The LLM provider has moved from Gemini → xAI Grok → Anthropic Claude → Groq, all in the search for a genuinely free-to-use API (Gemini's free tier was too rate-limited at ~20 requests/day; xAI and Anthropic both require paid billing before any call succeeds) — it now targets Groq (`app/llm/client.py`, via the `openai` SDK pointed at Groq's OpenAI-compatible endpoint, defaulting to `openai/gpt-oss-20b` and escalating to `openai/gpt-oss-120b` only on a repair retry). `pytest -m live` has been re-run against real Groq: `test_llm.py` and `test_pipeline.py` (all 7, after fixing a `check_hallucinations()` alias bug the migration surfaced — see the SQL Generation & Validation entry above) pass; `test_api.py`/`test_e2e.py`'s live cases are still outstanding via `pytest`, though the equivalent HTTP path has been exercised manually. Beyond that, what's left per [`docs/MODULES.md`](docs/MODULES.md) is deliberately deferred: OAuth2/OIDC auth + role-based schema visibility, Redis caching, Docker/Kubernetes deployment, and Grafana dashboards (§6.5, §9 of [`enterprise-text-to-sql-architecture.md`](enterprise-text-to-sql-architecture.md)) — none needed for local development, all picked up only when there's a concrete reason to.