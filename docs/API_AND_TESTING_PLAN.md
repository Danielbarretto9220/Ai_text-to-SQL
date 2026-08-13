# API & App Module + End-to-End Testing — Implementation Plan

Plan for the final phase of [`MODULES.md`](MODULES.md)'s "API & app (§6)" section, plus the project's
first test suite. Section references (§) point at
[`enterprise-text-to-sql-architecture.md`](../enterprise-text-to-sql-architecture.md).

Written 2026-08-13, for implementation in a later session. This document is self-contained — it assumes no
context beyond the repository itself.

## Scope decisions (already made — don't re-litigate)

**In scope:** FastAPI service with all 7 endpoints from §6.4, a Streamlit UI, basic `/metrics` +
structured logging, and a full live end-to-end test suite.

**Explicitly deferred** (leave as ⬜ in `MODULES.md`, don't half-build):
- OAuth2/OIDC auth + role-based schema visibility (§6.5) — needs an external IdP tenant. Note:
  `meta.tables` has **no `allowed_roles` column**; it does not exist and is deliberately *not* being added
  speculatively.
- Redis caching (§6.5, §9) — needs a running Redis server; a performance concern, not correctness.
- Docker/Kubernetes (§6.5), Grafana dashboards (§6.2).
- Async/parallel retrieval, streaming responses, conversational memory (§9–§10).

**Testing approach:** all tests hit the **real** Gemini API and real database — chosen deliberately over
mocking, because the point is verifying the real integration. This has consequences the test design must
handle; see "Live-test discipline" below. If a future session wants to add mocks, that's a new decision,
not an incidental one.

## Current state (verified at time of writing — re-check before editing)

Everything up to and including SQL validation is built and working. `app/pipeline.py`'s
`generate_validated_sql(connection, question_text, embedding_model=None, reranker_model=None)` runs
retrieval → prompt → LLM → validate (with one repair retry) and returns `{question, sql, valid, errors,
warnings, tables_used, confidence, retrieval, cost, retried_for_validation}`.
`execute_query(connection, sql_text, row_cap=1000, statement_timeout_ms=5000)` runs a validated SELECT
inside a `READ ONLY` transaction with a statement timeout, always rolled back.

**All four API files are docstring-only stubs** (`app/main.py`, `app/api/routes_query.py`,
`routes_feedback.py`, `routes_admin.py`); `app/api/__init__.py` is empty. `tests/` contains only an empty
`__init__.py`. There is no `pytest.ini`, `conftest.py`, or `pyproject.toml` anywhere in the repo.

Two facts that drive real work below:

1. **No feedback or query-log table exists.** The `meta` schema has 9 tables, none of which store query
   history or user verdicts. `meta.query_patterns` (the closest) has only `pattern_id,
   intent_description, example_question, sql_template, tables_used` — no user, timestamp, or verdict.
   → a new `METADATA/20_*.sql` migration is required.
2. **`POST /api/v1/execute` is listed in §6.4 but missing from `MODULES.md`'s API table.** It is a real
   endpoint to build (backed by the existing `execute_query()`), and the `MODULES.md` omission is a doc
   bug to fix as part of this work.

New pip dependencies: `fastapi`, `uvicorn`, `streamlit`, `pytest`. Note `httpx` and `prometheus-client`
are **already installed** (`httpx` arrived via `google-genai`) but are **not pinned in
`requirements.txt`** — add all of them, pinned to installed versions.

---

## Part A — API & app

### A1. `METADATA/20_add_query_log_and_feedback.sql` (new migration)

Two tables, following the existing migrations' idempotent style (`CREATE TABLE IF NOT EXISTS`).

`meta.query_log` — one row per generated query (§1.1: "Runtime query logs, feedback, approved SQL →
PostgreSQL … auditability, fine-tuning corpus, few-shot example bank"):

```
query_id SERIAL PK, question TEXT NOT NULL, generated_sql TEXT, is_valid BOOLEAN,
errors JSONB, warnings JSONB, tables_used TEXT[], llm_confidence TEXT,
retrieval_confidence NUMERIC, retrieval_label TEXT, estimated_cost NUMERIC,
estimated_rows BIGINT, retried_for_validation BOOLEAN, prompt_version INT,
latency_ms INT, created_at TIMESTAMPTZ DEFAULT now()
```

`meta.query_feedback` — user verdicts, referencing a logged query:

```
feedback_id SERIAL PK, query_id INT REFERENCES meta.query_log(query_id) ON DELETE CASCADE,
is_correct BOOLEAN NOT NULL, corrected_sql TEXT, comment TEXT,
promoted_to_pattern_id INT REFERENCES meta.query_patterns(pattern_id),
created_at TIMESTAMPTZ DEFAULT now()
```

`promoted_to_pattern_id` closes §10's "feedback loop feeding a few-shot example bank" — it records when an
approved query was promoted into `meta.query_patterns`.

Then add matching `MetaQueryLog` / `MetaQueryFeedback` models to `app/db/models.py`. **This is mandatory,
not optional** — that file's own docstring states `METADATA/*.sql` is the DDL source of truth and "If the
DDL changes, update both." Add a loader to `app/db/metadata_loader.py` only if something actually needs one
(don't add unused loaders).

### A2. `app/config.py` — extend

Currently holds only `GEMINI_API_KEY` / `GEMINI_MODEL`. Add, keeping the **existing module-level
`os.getenv()` convention** (no Pydantic `BaseSettings` class — `MODULES.md` explicitly records that no
settings-class abstraction was introduced, and `workers/scheduler.py` uses the same plain-constant
pattern):

`API_HOST`, `API_PORT`, `EXECUTE_ENABLED` (default **false**), `EXECUTE_ROW_CAP`,
`EXECUTE_STATEMENT_TIMEOUT_MS`, `LOG_LEVEL`, `API_BASE_URL` (used by the Streamlit UI).

`EXECUTE_ENABLED` implements §4 stage 6's "Execution (optional, feature-flagged)". It must default to
**off** — `execute_query()` is the only path in this project that runs LLM-generated SQL against the real
database, and the existing design keeps it opt-in.

### A3. `app/api/schemas.py` (new) — Pydantic request/response models

Distinct from `app/llm/schemas.py` (which models the *LLM's* output). Needed: `QueryRequest`,
`QueryResponse`, `ExecuteRequest`, `ExecuteResponse`, `FeedbackRequest`, `FeedbackResponse`,
`SchemaSearchResponse`, `HealthResponse`, `ReindexResponse`.

`QueryResponse` must include the `query_id` from `meta.query_log`, because `POST /api/v1/feedback`
references it. This is the contract that makes the feedback loop work — get it right first.

### A4. `app/main.py` — FastAPI entrypoint

**The single most important design point in this phase:** load the embedding model
(`app/retrieval/vector_search.load_embedding_model()`) and the cross-encoder reranker
(`app/retrieval/rerank.load_reranker_model()`) **once at startup** via FastAPI's `lifespan` context
manager, storing them on `app.state`. Each takes several seconds to load; loading them per-request would
make every API call unusably slow. Every route must reuse the shared instances —
`generate_validated_sql()` already accepts them as parameters precisely so they can be injected.

Also: `include_router` for the three route modules; structured logging configured from `LOG_LEVEL` (use
stdlib `logging` — `workers/scheduler.py` already establishes that precedent over `print()` for
long-running processes); CORS allowing the Streamlit origin; and a generic exception handler returning
clean JSON rather than leaking tracebacks.

DB connections: a FastAPI dependency that opens a connection per request via
`app/db/session.get_connection()` and closes it in a `finally`. Connection pooling is a known future
improvement — note it, don't build it.

### A5. Routes

**`app/api/routes_query.py`**
- `POST /api/v1/query` — `{question, execute?}` → runs `generate_validated_sql()` using the shared models,
  writes a `meta.query_log` row (capturing latency), returns the result plus `query_id`. Honors `execute`
  **only** if `EXECUTE_ENABLED` is true *and* validation passed; otherwise returns SQL without results.
- `POST /api/v1/execute` — the §6.4 endpoint currently missing from `MODULES.md`. Takes previously-returned
  SQL (or a `query_id`) and **re-runs `validate_sql()` before executing** — never trust a client-supplied
  SQL string just because an earlier response contained one — then calls `execute_query()`. Gated on
  `EXECUTE_ENABLED`, returning HTTP 403 when disabled.

**`app/api/routes_feedback.py`**
- `POST /api/v1/feedback` — `{query_id, is_correct, corrected_sql?, comment?}` → inserts into
  `meta.query_feedback`. When feedback is positive (or supplies a correction), optionally promote it into
  `meta.query_patterns` and set `promoted_to_pattern_id`. Promotion should be explicit (a `promote: bool`
  field), not an automatic side effect — silently mutating the few-shot bank that drives future retrieval
  quality is not something a thumbs-up should do by itself.

**`app/api/routes_admin.py`**
- `GET /api/v1/schema/search?q=` — debug retrieval endpoint; call `retrieve_context()` (or
  `hybrid_search()` directly) and return the ranked documents.
- `POST /api/v1/admin/reindex` — calls `workers.reindex_embeddings.incremental_reindex()`.
- `GET /api/v1/health` — DB reachable, models loaded, `GEMINI_API_KEY` present. Must **not** make a live
  Gemini call (health checks get polled; that would bill on every poll).
- `GET /metrics` — Prometheus exposition. Note it is at `/metrics`, **not** under `/api/v1/` (per §6.4).

### A6. Observability

`prometheus-client` is already installed. Counters: queries generated, validation failures, LLM repair
retries, executions performed, feedback submitted. Histogram: end-to-end query latency. Keep it small —
increment from the routes, don't thread metrics through the pipeline internals.

### A7. `ui/streamlit_app.py` (new top-level `ui/` directory)

The UI must call the FastAPI service **over HTTP** (`API_BASE_URL`), not import `app.pipeline` directly —
§6.2 models Streamlit as a client of the API (`ST --> EP`), and importing the pipeline would duplicate the
model-loading problem inside a second process.

Features: question input; generated SQL (syntax-highlighted); validation status with errors and warnings
shown distinctly (warnings are advisory — guardrails deliberately don't fail a query on them); confidence
(both retrieval confidence and the LLM's self-reported confidence — they legitimately differ, see caveats);
selected tables and join paths; an Execute button (visible only when `EXECUTE_ENABLED`); results table; and
thumbs up/down + optional correction posting to `/api/v1/feedback`.

---

## Part B — End-to-end test suite

### B1. Infrastructure

- **`pytest.ini`** — register markers: `live` (makes real Gemini calls) and `slow`. Even though all tests
  use the live DB, marking the LLM-calling ones lets you run the fast subset with `-m "not live"` while
  iterating.
- **`tests/conftest.py`**
  - **Session-scoped** fixtures: `db_connection`, `embedding_model`, `reranker_model`, and the FastAPI
    `TestClient`. Session scope is essential — reloading the MiniLM + cross-encoder models per test would
    add minutes to every run.
  - **Function-scoped** `db_transaction` fixture: `BEGIN` before, `ROLLBACK` after, always. This is how
    feedback/query-log writes stay out of your real data.
  - **Critical subtlety:** API routes open their *own* DB connections via dependency injection, so a
    test-level transaction on a *different* connection will not roll back writes made inside a request.
    Use `app.dependency_overrides` to inject the test's transaction-bound connection into the app for API
    tests. Without this, rollback isolation silently does nothing and test rows quietly accumulate in the
    dev database.
  - **`retry_on_api_error` helper** — retries a callable on `google.genai.errors.ServerError` (transient
    503 "model overloaded") a couple of times with a short backoff. The Gemini API returned a transient 503
    during earlier development; without this, the suite will intermittently fail for reasons unrelated to
    the code.

### B2. Live-test discipline (read before writing assertions)

Because every test hits a real, non-deterministic LLM:

- **Assert structure and semantics, never exact SQL strings.** The model will not emit byte-identical SQL
  across runs — it has already been observed alternating between `= 'Overdue'` and `ILIKE 'overdue'` for
  the same question. Good assertions: `result["valid"] is True`; `"emi_payments" in result["tables_used"]`;
  the SQL parses via `sql_parser.parse_sql()`; `is_read_only()` is true; every referenced column exists
  (reuse `check_hallucinations()`); `LIMIT` present for non-aggregate queries. Bad assertion:
  `assert result["sql"] == "SELECT ..."`.
- **Share one LLM call across many assertions.** Make the pipeline result a session-scoped fixture
  parameterized by question, then assert against it repeatedly — don't call `generate_validated_sql()` once
  per assertion. Budget roughly 15–25 live Gemini calls for a full run; on a flash-class model that's a
  trivial cost, but it's the difference between a 2-minute and a 20-minute suite.
- **Don't assert on the LLM's self-reported `confidence` field.** It's a model opinion and will vary.

### B3. Test files

- **`tests/test_db.py`** — connectivity; all six loaders in `app/db/metadata_loader.py` return expected
  counts (currently 5 tables / 30 columns / 6 relationships / 12 glossary terms / 15 query patterns /
  8 business rules — re-derive these rather than hardcoding blindly if the data has changed); ORM models
  match live DDL.
- **`tests/test_retrieval.py`** — vector search returns results; `keyword_search()` returns results; RRF
  fusion surfaces at least one document the vector leg alone missed; reranking changes the ordering;
  `get_join_path("emi_payments", "customers")` returns the two-hop path via `loans`;
  `get_join_path(x, x) == []`; `retrieve_context()` returns the documented keys.
- **`tests/test_prompting.py`** — `get_active_prompt()` returns the active `text_to_sql_system_prompt`;
  `assemble_context()` includes only the selected tables (not the whole 5-table catalog); the rendered user
  prompt contains valid JSON in its CONTEXT block and correctly-rendered literal braces in the OUTPUT
  FORMAT section.
- **`tests/test_validation.py`** — the highest-value, fastest file; **no LLM calls**. The 7 parser
  scenarios (valid single-table, valid join, unknown table, unknown column, unsupported join, non-read-only
  INSERT, syntax error); all 8 seeded business rules trigger with correct severity; LIMIT injected on
  non-aggregates but not pure aggregates; complexity caps; cost estimator thresholds.
  Include a **regression test for the unqualified-column bug** fixed during the validation phase: a rule
  violation written without table prefixes (e.g. `SELECT SUM(interest_rate) FROM loans`) must still be
  caught. That bug silently disabled 3 of 8 business rules and is easy to reintroduce.
- **`tests/test_llm.py`** (live) — `call_llm()` returns a parseable `SQLGenerationResponse`; an
  out-of-scope question ("what is the weather in Mumbai") returns the `insufficient_context` error branch.
- **`tests/test_pipeline.py`** (live) — `generate_validated_sql()` on 3–5 canonical banking questions
  returns `valid=True` with structurally sound SQL; `execute_query()` returns rows for a safe SELECT; and
  the **defense-in-depth test**: calling `execute_query()` directly with an `UPDATE` (bypassing all Python
  validation) must raise, and the target row must be verifiably unchanged afterward.
- **`tests/test_api.py`** (live) — every one of the 7 endpoints via `TestClient`, including: `/health`
  without a live LLM call; `/api/v1/execute` returning 403 when `EXECUTE_ENABLED` is false;
  `/api/v1/query` persisting a `meta.query_log` row and returning its `query_id`.
- **`tests/test_e2e.py`** (live) — the full user journey in one test: `POST /api/v1/query` →
  `POST /api/v1/execute` → `POST /api/v1/feedback` with the returned `query_id`, asserting the feedback row
  lands and (when `promote` is set) a `meta.query_patterns` row is created and linked via
  `promoted_to_pattern_id`.

---

## Part C — Docs to update when done

- **`docs/MODULES.md`** — mark the API rows ✅; **add the missing `POST /api/v1/execute` row** (fixing the
  discrepancy against §6.4); add rows for `METADATA/20_*.sql`, `app/api/schemas.py`, `ui/streamlit_app.py`,
  and a new Testing section; keep auth/Redis/Docker/monitoring explicitly ⬜ with a note that they were
  deliberately deferred, not forgotten.
- **`README.md`** — project-structure tree; new dependencies; how to run the API
  (`uvicorn app.main:app --reload`), the UI (`streamlit run ui/streamlit_app.py`), and the tests
  (`pytest`, plus the warning that the default run makes real, billable API calls); a `✔` Current Progress
  entry; and a rewritten Next Steps.
- **`CLAUDE.md`** — the API layer's architecture (especially the lifespan model-loading requirement and the
  `EXECUTE_ENABLED` gate), how to run everything, and the live-test cost caveat.
- **`.env`** — add the new settings. The API key must never be committed; `.env` is gitignored — keep it
  that way.

## Part D — Suggested execution order

Each step is independently verifiable; don't move on until the current one runs.

1. Migration 20 + ORM models → verify via `python -m app.db.metadata_loader`.
2. `app/config.py` + `app/api/schemas.py`.
3. `app/main.py` with lifespan model loading + `/health` → verify `uvicorn` starts and `/health` responds
   quickly (proves models loaded once, at startup).
4. `routes_query.py` (`/query`, `/execute`) → verify via the `/docs` Swagger UI.
5. `routes_feedback.py`, `routes_admin.py`.
6. `/metrics` + structured logging.
7. Streamlit UI.
8. Test infrastructure (`pytest.ini`, `conftest.py`), then the test files in B3's order —
   `test_validation.py` first, since it's fastest and needs no LLM.
9. Docs.

## Known caveats to carry forward (documented behavior, not bugs to "fix")

- **Retrieval confidence and LLM confidence legitimately disagree.** The cross-encoder reranker was trained
  on passage-relevance data, so it scores aggregation-style questions ("which branch has the most defaulted
  loans") as `low` confidence even when table selection is correct — while the LLM then produces correct
  SQL and self-reports `high`. Both the prompt builder and LLM client deliberately do **not** short-circuit
  on `clarification_needed`. The UI should surface both numbers rather than trying to reconcile them, and
  tests should not assert they agree.
- **`GEMINI_MODEL` defaults to the `gemini-flash-latest` alias**, not a pinned version — a pinned string
  (`gemini-2.5-flash`) went stale mid-project when Google retired it for new API keys. Keep the alias.
- **Warnings are advisory.** Guardrails deliberately don't fail a query on `warning`-severity business-rule
  hits; only `error` severity blocks. Preserve that distinction in the API response and the UI.
