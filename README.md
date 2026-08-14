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

The repo is laid out to match the target architecture in [`enterprise-text-to-sql-architecture.md`](enterprise-text-to-sql-architecture.md). Most of `app/` and `workers/` are stub modules (docstring only, no logic yet) marking where each planned piece will live — see [`docs/MODULES.md`](docs/MODULES.md) for the full build-out checklist and status of every module.

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
│   ├── llm/                   client.py (Gemini via google-genai) + schemas.py (implemented)
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
│                               llm/pipeline/api/e2e (live, real Gemini calls) (implemented)
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
  `sentence-transformers`, `sqlalchemy`, `pgvector`, `apscheduler`, `google-genai`, `pydantic`, `sqlglot`,
  `fastapi`, `uvicorn`, `streamlit`, `pytest`, `httpx`, `prometheus-client`, `requests`)
  - `sentence-transformers` generates embeddings locally (`all-MiniLM-L6-v2`) and drives the reranker
    (`cross-encoder/ms-marco-MiniLM-L-6-v2`); pulls in `torch`/`transformers`
  - `pgvector` is the Python package (not the Postgres extension) — provides `pgvector.sqlalchemy.Vector`
  - `apscheduler` drives `workers/scheduler.py`'s interval-based auto-sync trigger
  - `google-genai` is the Gemini SDK used by `app/llm/client.py`; `pydantic` backs `app/llm/schemas.py`'s
    structured-output models
  - `fastapi` + `uvicorn` serve the HTTP API (`app/main.py`); `streamlit` + `requests` drive the UI
    (`ui/streamlit_app.py`); `prometheus-client` backs `/metrics`; `pytest` + `httpx` (the latter required
    by FastAPI's `TestClient`) run the test suite
- **Internet access on first run**, to download the `all-MiniLM-L6-v2` embedding model and the
  `cross-encoder/ms-marco-MiniLM-L-6-v2` reranker model from Hugging Face Hub, and to call the Gemini API
- A **`.env` file** in the project root (not included in the repo) defining:
  ```
  DB_HOST=localhost
  DB_PORT=5432
  DB_NAME=your_db_name
  DB_USER=your_db_user
  DB_PASSWORD=your_db_password
  GEMINI_API_KEY=your_google_ai_studio_api_key
  GEMINI_MODEL=gemini-flash-latest
  API_HOST=127.0.0.1
  API_PORT=8000
  API_BASE_URL=http://127.0.0.1:8000
  EXECUTE_ENABLED=false
  EXECUTE_ROW_CAP=1000
  EXECUTE_STATEMENT_TIMEOUT_MS=5000
  LOG_LEVEL=INFO
  ```
  `GEMINI_API_KEY` is from [Google AI Studio](https://aistudio.google.com/). `GEMINI_MODEL` is optional
  (defaults to `gemini-flash-latest`, a model-family alias that stays current without needing code changes
  as Google ships newer generations — a pinned model string like `gemini-2.5-flash` can and did go stale
  mid-project). `EXECUTE_ENABLED` gates `app/pipeline.py`'s `execute_query()` — the only code path that
  runs LLM-generated SQL against the real database — and defaults to **false**; the rest have working
  defaults and only need overriding if you want different values.

  **Free-tier note:** a free Google AI Studio API key is capped at 20 `generate_content` calls **per day**
  per model. The live pytest suite alone (see Testing below) uses roughly a dozen; manual UI testing eats
  into the same budget.

There's no `pyproject.toml`/packaging yet, so run modules from the repo root with `-m` so `app`/`workers`/`tests` resolve as packages, e.g. `python -m workers.reindex_embeddings`.

### Running the API, UI, and tests

```
uvicorn app.main:app --reload             # FastAPI service at http://127.0.0.1:8000 (Swagger UI at /docs)
streamlit run ui/streamlit_app.py         # Streamlit UI at http://localhost:8501 (needs the API running)
pytest                                    # full suite — see the free-tier note above; live tests are billable
pytest -m "not live"                      # fast subset, no Gemini calls (safe to run anytime)
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

✔ LLM Client (app/llm/client.py — Google AI Studio/Gemini via the google-genai SDK; app/llm/schemas.py — a single Pydantic SQLGenerationResponse covering both the normal SQL-response and insufficient_context escape-hatch branches of the seeded system prompt. Live-verified end to end: a lookup question, an aggregation question the retrieval layer flagged low-confidence for, and an out-of-scope question that correctly triggered the insufficient_context response)

✔ SQL Generation & Validation (app/validation/sql_parser.py — sqlglot-based syntax/read-only/hallucination/join checks; guardrails.py — LIMIT injection, complexity limits, and a defensive per-rule_type business rules engine over meta.business_rules' genuinely heterogeneous rule_logic shapes; cost_estimator.py — EXPLAIN-based cost/row thresholds. app/pipeline.py ties it all together as generate_validated_sql() — retrieval → prompt → LLM → validate → one repair-retry on validation failure — plus an opt-in execute_query() with real safety rails (read-only transaction, statement timeout, row cap, always rolled back). Live-verified end to end including the repair-retry path and execute_query()'s defense in depth: a direct UPDATE attempt bypassing all validation was rejected by Postgres's own READ ONLY transaction, not just the Python guardrails)

✔ API & App (app/main.py — FastAPI service loading the embedding/reranker models once at startup via `lifespan`; app/api/routes_query.py, routes_feedback.py, routes_admin.py — all 7 endpoints from the architecture doc's §6.4, including `POST /api/v1/execute` which always re-validates a query server-side before running it, and `GET /api/v1/health` which never makes a live Gemini call so polling doesn't bill the API; app/api/schemas.py, deps.py, metrics.py; ui/streamlit_app.py — a Streamlit client that talks to the API over HTTP, never importing the pipeline directly. METADATA/20_add_query_log_and_feedback.sql adds meta.query_log/meta.query_feedback, closing the feedback-loop-into-the-few-shot-bank design from the architecture doc's §10. Manually verified end to end: all 7 endpoints exercised via curl and Swagger, the Streamlit UI driven in a real browser session, and a transient live-Gemini 503 confirmed to surface cleanly in the UI without corrupting any logged state)

✔ Test Suite (pytest.ini + tests/conftest.py — session-scoped model/DB fixtures, a TestClient wired to a test-controlled DB connection via `app.dependency_overrides`, and retry helpers for transient Gemini errors. tests/test_validation.py, test_db.py, test_retrieval.py, test_prompting.py — 55 tests, no LLM calls, all green. tests/test_llm.py, test_pipeline.py, test_api.py, test_e2e.py — 13 `live`-marked tests covering the full generation → validation → execution → feedback journey; written and one live path already manually verified working end to end, but a full live run couldn't complete in the same session because the free-tier Gemini API key is capped at 20 `generate_content` calls/day and testing across this phase exhausted that budget — re-run `pytest -m live` once it resets)

---

## Next Steps

Everything in [`docs/API_AND_TESTING_PLAN.md`](docs/API_AND_TESTING_PLAN.md) is built. What's left, per [`docs/MODULES.md`](docs/MODULES.md), is deliberately deferred: OAuth2/OIDC auth + role-based schema visibility, Redis caching, Docker/Kubernetes deployment, and Grafana dashboards (§6.5, §9 of [`enterprise-text-to-sql-architecture.md`](enterprise-text-to-sql-architecture.md)) — none needed for local development, all picked up only when there's a concrete reason to. In the meantime: re-run `pytest -m live` once the daily Gemini quota resets to get a clean full-suite run on record.