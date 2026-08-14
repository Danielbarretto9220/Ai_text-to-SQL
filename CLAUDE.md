# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A banking-domain Text-to-SQL system being built incrementally toward the target design in
[`enterprise-text-to-sql-architecture.md`](enterprise-text-to-sql-architecture.md). Two things coexist in this repo:

1. **A real PostgreSQL banking database** (`SQL/`) — `branches`, `customers`, `loan_officers`, `loans`,
   `emi_payments` — with dummy data.
2. **A metadata + retrieval layer** (`METADATA/`, `app/`, `workers/`) that describes that database for an LLM:
   table/column descriptions, business synonyms, sample values, FK relationships, a business glossary, a
   few-shot query-pattern bank, and pgvector embeddings over all of it.

**Always check [`docs/MODULES.md`](docs/MODULES.md) before touching `app/` or `workers/`** — it is the
authoritative, up-to-date status table (✅/🟡/⬜) of every module against the architecture doc. A few items
are deliberately deferred (auth, Redis, Docker/K8s, Grafana — see `docs/MODULES.md`'s API & app section);
don't assume something is unbuilt just because the architecture doc mentions it.

## Current implementation status (see docs/MODULES.md for details)

**Implemented (real logic):**
- `METADATA/01-18_*.sql` — the whole `meta` schema and its population (tables, columns, relationships,
  business glossary, query patterns, change log, prompt versions, business rules, drift support)
- `app/db/session.py`, `app/db/metadata_loader.py`, `app/db/models.py` (SQLAlchemy ORM over `meta.*`)
- `app/retrieval/` — `document_builder.py`, `vector_search.py`, `hybrid_search.py`, `rerank.py`,
  `relationship_graph.py`, `confidence.py` (the full retrieval pipeline — see below)
- `app/prompting/prompt_builder.py` + `app/prompting/templates/user_prompt.txt` (see below)
- `app/llm/client.py` (Gemini via `google-genai`) + `app/llm/schemas.py` (see below)
- `app/config.py` (`GEMINI_API_KEY`/`GEMINI_MODEL` plus `API_HOST`/`API_PORT`/`API_BASE_URL`,
  `EXECUTE_ENABLED`/`EXECUTE_ROW_CAP`/`EXECUTE_STATEMENT_TIMEOUT_MS`, `LOG_LEVEL`)
- `app/validation/sql_parser.py`, `guardrails.py`, `cost_estimator.py` + `app/pipeline.py` (see below)
- `workers/reindex_embeddings.py`, `workers/generate_docs.py`, `workers/drift_detector.py`,
  `workers/sync_data_content.py`, `workers/scheduler.py`
- `app/main.py` (FastAPI entrypoint), `app/api/routes_query.py`, `routes_feedback.py`, `routes_admin.py`,
  `deps.py`, `schemas.py`, `metrics.py`, `ui/streamlit_app.py` (see "API layer" below)
- `tests/` — `test_validation.py`, `test_db.py`, `test_retrieval.py`, `test_prompting.py` (fast, no LLM),
  `test_llm.py`, `test_pipeline.py`, `test_api.py`, `test_e2e.py` (`live`-marked, real Gemini calls)

Nothing is currently a docstring-only stub. `docs/MODULES.md` is still the authoritative status table if
that changes — check it before assuming a file has real logic.

## Running things

No `pyproject.toml`/packaging yet — always run modules from the repo root with `-m` so `app`/`workers`
resolve as packages:

```
python -m app.db.metadata_loader
python -m app.db.models
python -m workers.reindex_embeddings
python -m workers.generate_docs
python -m workers.drift_detector
python -m workers.sync_data_content
python -m workers.scheduler        # long-running; Ctrl+C to stop
python -m app.retrieval.vector_search
python -m app.retrieval.hybrid_search
python -m app.retrieval.rerank
python -m app.retrieval.relationship_graph
python -m app.retrieval.confidence  # full retrieval pipeline demo
python -m app.prompting.prompt_builder  # full prompting pipeline demo
python -m app.llm.client  # full pipeline demo incl. a real Gemini call
python -m app.validation.sql_parser
python -m app.validation.guardrails
python -m app.validation.cost_estimator
python -m app.pipeline  # full end-to-end pipeline demo (retrieval -> prompt -> LLM -> validate)
python test_connection.py     # standalone DB connectivity smoke test, run directly (not -m)

uvicorn app.main:app --reload           # FastAPI service (http://127.0.0.1:8000, Swagger UI at /docs)
streamlit run ui/streamlit_app.py       # Streamlit UI (needs the API running; http://localhost:8501)

pytest                                  # full suite — see "Live-test cost" below before running
pytest -m "not live"                    # fast subset (55 tests), no Gemini calls — safe to run anytime
pytest -m live                          # live subset (13 tests), real billable Gemini calls
```

`pip install -r requirements.txt` installs pinned dependencies. No lint/format config in the repo.

### Live-test cost

A free-tier Gemini API key is capped at **20 `generate_content` calls per day per model** — not a
per-minute limit (the SDK's own `RetryInfo` hint, e.g. "retry in 9s", is misleading here; the actual
blocking quota is `GenerateRequestsPerDayPerProjectPerModel-FreeTier` and doesn't reset for hours). A
single `pytest -m live` run costs roughly a dozen calls, and manual UI/curl smoke testing draws from the
same budget. If `pytest -m live` starts failing with `429 RESOURCE_EXHAUSTED`, that's quota exhaustion, not
a bug — don't retry-loop against it; wait for the daily reset or use a paid-tier key. Distinguish this from
a transient `503 UNAVAILABLE` ("model experiencing high demand"), which genuinely is worth a short retry —
`tests/conftest.py`'s `retry_on_api_error`/`retry_on_5xx` helpers handle that case.

### Environment

Requires a local `.env` (gitignored) with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, plus
`GEMINI_API_KEY` (from [Google AI Studio](https://aistudio.google.com/)) and optionally `GEMINI_MODEL`
(defaults to `gemini-flash-latest` — a model-family alias, not a pinned version string; a pinned string
like `gemini-2.5-flash` went stale mid-project when Google moved new API keys to newer model generations,
so prefer the `-latest` alias over pinning unless a specific model's behavior is required) — a PostgreSQL
instance with the **pgvector** extension enabled. Also: `API_HOST`/`API_PORT`/`API_BASE_URL` (working
defaults, `127.0.0.1:8000`), `EXECUTE_ENABLED` (default **false** — gates `app/pipeline.py`'s
`execute_query()`, the only code path that runs LLM-generated SQL against the real database),
`EXECUTE_ROW_CAP`/`EXECUTE_STATEMENT_TIMEOUT_MS`, `LOG_LEVEL`. Embeddings are generated locally via
`sentence-transformers/all-MiniLM-L6-v2` (384-dim vectors), which pulls in `torch`/`transformers` and needs
internet access on first run to pull the model from Hugging Face; the LLM client needs internet access for
every call (it's a live API, no local fallback).

Key packages: `psycopg2`, `python-dotenv`, `sqlalchemy` (2.0), `pgvector` (Python package, for
`pgvector.sqlalchemy.Vector`), `sentence-transformers` (also provides `CrossEncoder`, used by
`app/retrieval/rerank.py` — no separate reranking package needed), `apscheduler` (drives
`workers/scheduler.py`), `google-genai` (Gemini SDK — chosen over the legacy `google-generativeai` package),
`pydantic` (backs `app/llm/schemas.py`), `sqlglot` (chosen over `pglast` for `app/validation/sql_parser.py`
— `pglast` needs native compilation against the PG C parser; `sqlglot` is pure Python, avoiding a repeat of
pgvector's Windows build pain). pgvector on Windows needs PG **17.3+** (17.0–17.2 has a Windows linker bug
that breaks building the extension from source). `fastapi` + `uvicorn` (the HTTP API), `streamlit` +
`requests` (the UI — calls the API over HTTP, doesn't import `app.pipeline`), `prometheus-client` (`/metrics`),
`pytest` + `httpx` (`httpx` is required by FastAPI's `TestClient`, not called directly).

## Architecture — how the pieces fit together

**Two separate database layers in the same PostgreSQL instance:**
- `public` schema — the actual banking warehouse (`SQL/01-06_*.sql`): the tables a generated SQL query
  would run against.
- `meta` schema — the metadata-about-the-warehouse layer (`METADATA/01-18_*.sql`): `meta.tables`,
  `meta.columns`, `meta.relationships`, `meta.business_glossary`, `meta.query_patterns`,
  `meta.document_embeddings` (pgvector), `meta.change_log`, `meta.prompt_versions`, `meta.business_rules`.
  This is the system of record; embeddings are a derived index that can always be rebuilt from it.

**Two DB access paths that intentionally coexist** — don't collapse them:
- `get_connection()` in `app/db/session.py` — raw psycopg2, used by all the original hand-written SQL
  modules (`metadata_loader.py`, `document_builder.py`, `reindex_embeddings.py`, `vector_search.py`,
  `generate_docs.py`, `drift_detector.py`).
- `get_engine()` / `get_session()` in `app/db/session.py` — SQLAlchemy, used only by the typed ORM layer
  in `app/db/models.py`.

**`app/db/models.py` is read/write convenience only, never schema authority.** `METADATA/*.sql` is the
source of truth for DDL — there is no `Base.metadata.create_all()` call anywhere. If you change the schema,
update the `.sql` file *and* the corresponding ORM model by hand; they're expected to be kept in sync
manually, not generated from each other.

**Content pipeline for the metadata layer** (`workers/`):
1. `generate_docs.py` introspects `information_schema`/`pg_constraint`/`pg_description` fresh on every run
   (structure — never goes stale) and merges in business content from `meta.*` as a best-effort second
   layer (never the reverse) → writes `docs/schema/*.md`. Full rebuild every run; **don't hand-edit
   `docs/schema/*.md`** — edit `METADATA/*.sql` or the live DDL instead.
2. `reindex_embeddings.py` embeds `meta.*` content into `meta.document_embeddings`, stamping a
   `content_hash` per row. `main()` does a full rebuild; `incremental_reindex()` only re-embeds rows whose
   `content_hash` changed and deletes rows for documents that no longer exist.
3. `drift_detector.py` diffs live `information_schema`/`pg_constraint` against `meta.tables`/`meta.columns`.
   On structural drift (column/table added/dropped, type/nullable/PK/FK changed — **not** row-count churn)
   it syncs `meta.*`, regenerates docs, and calls `incremental_reindex()`. Critical invariant: syncing
   structure must **never** overwrite `business_description`/`business_synonyms`/`sample_values` on
   existing rows — those come only from `METADATA/07-10_*.sql`. It only INSERTs new rows (business columns
   NULL) or UPDATEs structural columns on existing ones.

4. `sync_data_content.py` handles **data-content** drift — the complement to `drift_detector.py`'s
   structural drift. `row_count_estimate` and `sample_values` go stale from ordinary data changes with no
   DDL involved, and `drift_detector.py` deliberately never touches them. `run_full_sync()` runs structural
   sync first (order matters — a dropped column must be gone from `meta.columns` before the sample-values
   query runs against it), then refreshes row counts and sample values (by re-running
   `METADATA/10_populate_sample_values.sql`'s DO block), then unconditionally regenerates docs and
   re-embeds. `scheduler.py` (`APScheduler`, pure Python, portable) runs it on an interval
   (`SYNC_INTERVAL_MINUTES` env var) — `python -m workers.scheduler` is the only long-running process in
   this repo; everything else is one-shot.

Note: `meta.tables`/`meta.columns` have `BEFORE UPDATE`/`AFTER INSERT/UPDATE/DELETE` triggers that log to
`meta.change_log` — but `TRUNCATE` (used by `METADATA/03_populate_meta_tables.sql`) bypasses row-level
triggers, so a full reload of that script logs as fresh INSERTs, not DELETE+INSERT.

**Retrieval pipeline** (architecture doc §2.1, §2.2) — `app/retrieval/confidence.py`'s `retrieve_context()`
is the entry point, composing the other four modules in order:
1. `hybrid_search.py` — dense leg reuses `vector_search.py`'s `load_embedding_model`/
   `generate_query_embedding`/`search_documents`; sparse leg is `keyword_search()` against
   `meta.document_embeddings.content_tsv` (a `GENERATED ALWAYS AS (to_tsvector(...)) STORED` column + GIN
   index added by `METADATA/19_add_fulltext_search.sql`). Combined via `reciprocal_rank_fusion()`.
   `search_documents()` and `keyword_search()` both take an optional `document_types` filter (e.g.
   `["table", "column"]`) — default `None` preserves unfiltered search for existing callers.
2. `rerank.py` — `cross-encoder/ms-marco-MiniLM-L-6-v2` (via `sentence_transformers.CrossEncoder`) narrows
   the fused candidates down to a final top-k.
3. `relationship_graph.py` — `build_graph()` loads a bidirectional adjacency dict from
   `meta.relationships` (reuses `app/db/metadata_loader.load_relationship_metadata`, doesn't re-query).
   `get_related_tables()` expands the reranked table set with directly-joined tables; `get_join_path()`
   (BFS) resolves join paths between the final selected tables.
4. `compute_confidence()`/`needs_clarification()` in `confidence.py` blend the top rerank score with FK-graph
   connectivity into a confidence label, triggering a clarification flag on low confidence or two
   similar-scoring candidates from different tables. **Known calibration caveat**: the reranker was trained
   on passage-relevance data, so it scores aggregation-style questions ("which branch has the most
   defaulted loans") much lower than lookup-style ones, even with correct table selection — thresholds are
   left as tunable constants at the top of `confidence.py`, not hand-tuned against a handful of examples.

`retrieve_context()` scopes table selection to `document_type in ("table", "column")` specifically —
those are the only document types whose `metadata` carries `table_name` (glossary/query-pattern document
metadata doesn't), so they're what drives which tables get selected/expanded.

**Prompting** (architecture doc §3) — `app/prompting/prompt_builder.py`'s `build_prompt()` is the entry
point, composing `retrieve_context()` with prompt assembly:
1. `get_active_prompt()` reads the system prompt from `meta.prompt_versions` (`WHERE prompt_name = ... AND
   is_active`) — **this was already seeded** back in the Data Layer phase (`METADATA/14-15_*.sql`); the
   prompt text is not duplicated in Python. Raises if no active row exists rather than falling back silently.
2. `retrieve_context()` runs (reused from `app/retrieval/confidence.py`, not reimplemented).
3. `fetch_business_terms()`/`fetch_query_patterns()` — two small extra `hybrid_search()` calls
   (`document_types=["glossary"]` / `["query_pattern"]`) that close a real gap: the seeded prompt's rule 7
   ("prefer a matching query_pattern example") and architecture doc §3.2's `business_terms` context section
   both assume this content is available, but `retrieve_context()` itself only fetches
   `document_type in ("table", "column")`.
4. `assemble_context()` builds §3.2's CONTEXT shape by reusing `app/db/metadata_loader.py`'s existing
   `load_table_metadata`/`load_column_metadata` (filtered to the tables `retrieve_context()` selected) —
   not by re-parsing the free-text `content` field of retrieved documents.
5. `build_user_prompt()` interpolates the question + CONTEXT JSON into
   `app/prompting/templates/user_prompt.txt` (plain `.format()`, no templating library — none existed in
   the repo and only two interpolation points are needed).

`build_prompt()` deliberately does **not** short-circuit when `retrieval["clarification_needed"]` is set —
it still returns a fully-assembled prompt and surfaces the flag, leaving that policy decision (ask vs.
proceed anyway) to whichever future caller owns it.

**LLM client** (architecture doc §3.4, §6.5, §8) — `app/llm/client.py`'s `call_llm()` is the entry point,
taking `build_prompt()`'s output dict directly (no DB access, no retrieval re-run):
1. `get_client()` builds a `genai.Client(api_key=app.config.GEMINI_API_KEY)` — Google AI Studio/Gemini via
   the `google-genai` SDK.
2. `generate_sql()` calls `client.models.generate_content()` with `temperature=0` (§3.4 determinism) and
   `response_schema=SQLGenerationResponse` + `response_mime_type="application/json"` — Gemini enforces the
   output shape at generation time, stronger than prompt instructions alone.
3. `app/llm/schemas.py`'s `SQLGenerationResponse` is a single Pydantic model with every field optional,
   covering **both** branches of the seeded prompt's contract: a normal `{sql, tables_used, assumptions,
   confidence}` response, and the `{error: "insufficient_context", missing}` escape hatch (rule 1) — one
   model because Gemini's `response_schema` locks the model into exactly one schema, so both branches must
   be representable in it. `is_error_response()` lets callers branch.
4. On parse/validation failure, `call_llm()` does **one** hand-rolled repair retry (re-calls with the error
   appended, per §3.4) — not a generic retry library; that's a different concern (network transience, which
   this module doesn't handle — the SDK's own internal retry covers that, and did visibly exhaust once
   during testing on a transient `503`).

Live-verified: a lookup question generated correct SQL first-try; an aggregation question that the
retrieval layer flagged `low` confidence (the known reranker calibration caveat above) still produced
correct SQL with the LLM self-reporting `high` confidence — validating why `build_prompt()`/`call_llm()`
deliberately don't short-circuit on `clarification_needed`; and an out-of-scope question correctly
triggered the `insufficient_context` escape hatch.

`app/llm/client.py` does **not** do SQL validation, guardrails, cost estimation, or full pipeline
orchestration — those live in `app/validation/*` and `app/pipeline.py`, described next.

**SQL validation** (architecture doc §5) — three independent-but-composed modules, chosen `sqlglot`
(`dialect="postgres"`) over `pglast` deliberately: `pglast` binds to the real PG C parser and needs native
compilation, and this repo already has a documented, painful Windows build history with `pgvector`
(§17.0–17.2 linker bug). `sqlglot` is pure Python and covers everything needed.
1. `app/validation/sql_parser.py` — `parse_sql()` (syntax), `is_read_only()` (root node must be
   `exp.Select` — defense in depth, never trusts the LLM followed the system prompt's own read-only
   instruction), `check_hallucinations()` (resolves aliased/unqualified column refs against
   `meta.tables`/`meta.columns`), `check_joins()` (every JOIN...ON validated against
   `app/retrieval/relationship_graph.build_graph()`, reused not requeried).
2. `app/validation/guardrails.py` — `enforce_limit()` (injects `LIMIT 100` unless the query is a pure
   aggregate, matching system prompt rule 4), `check_complexity()` (join/subquery count caps),
   `check_business_rules()` (dispatches each active `meta.business_rules` row to a per-`rule_type` checker —
   the 8 seeded rules have 5 distinct `rule_logic` JSONB shapes, and even **inconsistent key names within
   the same `rule_type`**, so dispatch is defensive: unknown `rule_type` skipped, exceptions caught per-rule
   rather than crashing the whole check). **Bug found and fixed while implementing this**: the column
   resolver initially only handled `alias.column`-qualified references, silently missing every rule
   violation in unqualified single-table queries — which is how the LLM writes SQL most of the time (e.g.
   `SELECT SUM(interest_rate) FROM loans`, no table prefix). Fixed by resolving the empty-qualifier case to
   the query's sole table when unambiguous (mirrors the resolution `sql_parser.py`'s hallucination check
   already did correctly) — re-verify this if you touch either file, since it's an easy regression to
   reintroduce.
3. `app/validation/cost_estimator.py` — `EXPLAIN (FORMAT JSON)`, always safe/read-only regardless of
   whether the query is ever executed. Threshold constants are generous defaults for this project's tiny
   dataset, not tuned against real volume.

**Full pipeline orchestration** (architecture doc §4) — `app/pipeline.py`:
- `validate_sql()` combines all three validation modules into one `{valid, final_sql, errors, warnings,
  cost}` report. Skips the `EXPLAIN` cost check if hallucination/join errors exist (running `EXPLAIN`
  against a query that references a fake table/column would itself raise a DB error, not fail gracefully).
- `generate_validated_sql()` is the end-to-end entry point: `build_prompt()` → `call_llm()` →
  `validate_sql()` → on failure, **one** repair attempt — re-calls `call_llm()` with the validation errors
  appended to the user prompt. This is a **separate** retry loop from `call_llm()`'s own internal repair
  retry: that one fixes malformed *JSON shape*; this one fixes SQL *content* that fails validation
  (hallucinated table, forbidden aggregation, etc.), per architecture doc §5's exact "one automatic repair
  attempt" wording.
- `execute_query()` is **opt-in only** — never auto-invoked by `generate_validated_sql()`. This is the
  first code path in the whole project capable of running arbitrary LLM-generated SQL against the real
  database, so real safety rails apply: `SET TRANSACTION READ ONLY` + `statement_timeout` + row cap via
  `fetchmany()`, always `connection.rollback()`ed afterward, never committed. Live-verified as genuine
  defense in depth, not just a Python-level check: calling it directly with an `UPDATE` string (bypassing
  all validation entirely) is rejected by Postgres itself
  (`ReadOnlySqlTransaction cannot execute UPDATE in a read-only transaction`).

**API layer** (architecture doc §6.3, §6.4) — `app/main.py` exposes `app/pipeline.py` over HTTP:
1. **The single most important design point**: `app/main.py`'s `lifespan` context manager loads the
   embedding model and cross-encoder reranker **once at startup**, storing them on `app.state`. Each takes
   several seconds to load; loading per-request would make every API call unusably slow.
   `generate_validated_sql()` already accepts these as parameters precisely so they can be injected this
   way. Every route reuses the shared instances via `request.app.state.embedding_model`/`.reranker_model`
   (`app/api/deps.py`'s `get_db()` only handles the DB connection — models aren't a FastAPI dependency,
   to avoid a circular import between `app.api` and `app.main`).
2. A blanket `@app.exception_handler(Exception)` converts any unhandled exception (including a live
   `google.genai.errors.ServerError`) into a clean HTTP 500 JSON response rather than leaking a traceback.
   This matters for testing: it means `tests/conftest.py`'s FastAPI `TestClient`-based tests can't catch a
   `ServerError` as a raised exception — they have to check `response.status_code` instead (`retry_on_5xx`
   vs. `retry_on_api_error`, which is for direct, non-HTTP `call_llm()`/`generate_validated_sql()` calls).
3. `POST /api/v1/query` (`app/api/routes_query.py`) runs `generate_validated_sql()`, writes a
   `meta.query_log` row (`METADATA/20_add_query_log_and_feedback.sql`), and returns the row's `query_id` —
   the contract `POST /api/v1/feedback` depends on. `POST /api/v1/execute` **always re-validates** SQL via
   `validate_sql()` before calling `execute_query()`, even when the SQL comes from a previously-returned
   `query_id` — never trusting a client-supplied string just because an earlier response contained it.
   Both are gated by `EXECUTE_ENABLED` (default **false**); `/execute` returns HTTP 403 when it's off.
4. `POST /api/v1/feedback` (`routes_feedback.py`) inserts into `meta.query_feedback`; promoting the query
   into `meta.query_patterns` (the few-shot bank) requires an explicit `promote: true` in the request —
   never an automatic side effect of `is_correct: true`, since silently mutating the bank that drives
   future retrieval quality shouldn't happen without the caller asking for it.
5. `GET /api/v1/health` (`routes_admin.py`) checks DB reachability, models-loaded, and `GEMINI_API_KEY`
   presence — deliberately **never** makes a live Gemini call, since health checks get polled and polling
   shouldn't bill an external API. `GET /metrics` is Prometheus exposition (`app/api/metrics.py`'s
   counters/histogram) at the bare path, **not** under `/api/v1/`, per §6.4.
6. `ui/streamlit_app.py` calls the FastAPI service **over HTTP** (`API_BASE_URL`), never importing
   `app.pipeline` directly — §6.2 models Streamlit as a client of the API, and importing the pipeline would
   duplicate the model-loading problem inside a second process.

Manually verified end to end: all 7 endpoints via curl/Swagger, the Streamlit UI driven in a real browser
session (question → spinner → SQL/validation/confidence display → feedback), and a transient live-Gemini
`503` mid-session confirmed to surface cleanly in the UI without corrupting state (no `query_log` row is
written when the pipeline call raises, since that happens before the route's logging step).

**End-to-end pipeline status**: question → `retrieve_context()` → `build_prompt()` → `call_llm()` →
`validate_sql()` (+ one repair retry) → HTTP API → Streamlit UI is fully wired. Execution is wired but
deliberately opt-in (`execute_query()`/`EXECUTE_ENABLED`, never automatic). A first pytest suite exists
(`tests/`, see "Running things" and "Live-test cost" above) — 55 non-live tests are green; the 13 `live`
tests are written and one live path (a direct `/api/v1/query` call) was manually verified working, but a
full `pytest -m live` run hasn't completed clean in one sitting yet because of the free-tier daily quota —
re-run it once quota resets. What's left, all deliberately deferred per `docs/MODULES.md`: OAuth2/OIDC
auth + role-based schema visibility, Redis caching, Docker/Kubernetes, Grafana dashboards.

## Working conventions in this repo

- Follow the existing code style: heavy docstrings explaining *why* and pointing at the relevant
  architecture-doc section, generous blank lines between logical blocks, `print()`-based progress logging
  in one-shot scripts (`workers/`, the `python -m app.*` demos). `app/main.py` and the routes use stdlib
  `logging` instead, matching `workers/scheduler.py`'s precedent for long-running/request-serving code.
- Ask before adding new dependencies or diverging from the existing code/architecture pattern, even when
  you're confident in the alternative — this project follows the architecture doc closely and departures
  should be a deliberate, discussed choice.
- `docs/schema/*.md` and `docs/MODULES.md`'s status column are generated/status-tracking artifacts —
  regenerate `docs/schema/*.md` via `workers/generate_docs.py` rather than hand-editing, and update
  `docs/MODULES.md` when a stub becomes implemented.
