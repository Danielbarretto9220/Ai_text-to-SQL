# Modules Required to Complete the Project

Status of every module called for by `enterprise-text-to-sql-architecture.md`, mapped to its location in the repo. Legend: ✅ implemented · 🟡 partial (works standalone, not to the doc's full spec) · ⬜ not started (stub file only, no logic).

## Data layer (§1)

| Module | Location | Status | Notes |
|---|---|---|---|
| `meta` schema (tables, columns, relationships, business_glossary) | `METADATA/01-10_*.sql` | ✅ | Fully populated per README "Current Progress" — includes business/column descriptions, synonyms, and sample values (`10_populate_sample_values.sql` pulls real distinct values dynamically via a `DO` block, not hardcoded) |
| `meta.document_embeddings` (pgvector) | `METADATA/*.sql` | ✅ | Written to by `workers/reindex_embeddings.py`; pgvector 0.8.6 built from source on Windows (PG 17.3+ required — 17.0-17.2 has a Windows linker bug) |
| `meta.query_patterns` (few-shot bank) | `METADATA/11-12_*.sql` | ✅ | 15 hand-authored NL question → SQL template examples, embedded and retrievable like the other meta docs (§1.2, §10) |
| `meta.change_log` + `updated_at` trigger | `METADATA/13_create_change_log.sql` | ✅ | `meta.tables`/`meta.columns` get `BEFORE UPDATE` (bump `updated_at`) + `AFTER INSERT/UPDATE/DELETE` (log to `meta.change_log`) triggers; verified by a real row-count refresh (§1.6). Note: `TRUNCATE` (used by `03_populate_meta_tables.sql`) bypasses row-level triggers, so a full tables reload logs as fresh INSERTs, not DELETE+INSERT |
| `meta.prompt_versions` | `METADATA/14-15_*.sql` | ✅ | v1 system prompt seeded, adapted from architecture doc §3.1 for this project's flat (non-medallion) schema; partial unique index enforces one active version per `prompt_name` (§3.4). Not yet consumed by any code — `app/llm/client.py` is still a stub |
| `meta.business_rules` | `METADATA/16-17_*.sql` | ✅ | 8 hand-authored rules (structured JSONB `rule_logic`, engine-interpretable) grounded in real schema/data quirks — e.g. `emi_payments.amount_paid` is populated even on Missed/Overdue rows, so an unfiltered SUM overstates collections. Reuses the `meta.log_change()`/`set_updated_at()` triggers from `13_create_change_log.sql`. Not yet consumed — `app/validation/guardrails.py` (the rules engine that would read these) is still a stub (§5) |
| ORM/typed models over `meta.*` | `app/db/models.py` | ✅ | SQLAlchemy 2.0 declarative models for all 9 `meta.*` tables (mirrors live DDL, verified against `information_schema`/`pg_constraint`, not just the SQL source); `pgvector.sqlalchemy.Vector` for `document_embeddings.embedding`; `get_engine()`/`get_session()` added to `app/db/session.py` alongside the existing `get_connection()` (raw-SQL modules unchanged). Adds `sqlalchemy` + `pgvector` as new pip dependencies |
| DB connection handling | `app/db/session.py` | ✅ | Consolidated from the old per-script `get_connection()` |
| Metadata reader | `app/db/metadata_loader.py` | ✅ | Moved from `RAG/metadata_loader.py` |
| Auto-generated Markdown docs from `information_schema` | `workers/generate_docs.py` | ✅ | Writes `docs/schema/<table>.md` + index, per `public`-schema table. Two-tier: structure (columns, PK/FK, row estimate, `pg_description` comments) always fresh from the catalog; business content merged in from `meta.*` as a best-effort second layer. Full rebuild each run, no diffing (§1.7) |
| Drift detector (DDL change → re-embed) | `workers/drift_detector.py` | ✅ | Diffs live `information_schema`/`pg_constraint` against `meta.tables`/`meta.columns`; if structural drift found, syncs meta.\* (INSERT/UPDATE/DELETE — never touches business_description/synonyms/sample_values on existing rows), regenerates `docs/schema/*.md`, and incrementally re-embeds via `reindex_embeddings.incremental_reindex()`. True no-op if nothing changed. `METADATA/18_add_drift_support.sql` adds `content_hash` + the unique constraints the UPSERT logic needs (§1.6, §7) |
| Data-content refresh (row counts, sample values) | `workers/sync_data_content.py` | ✅ | Complements the drift detector: refreshes `meta.tables.row_count_estimate` (for *all* known tables, not just newly-created ones) and `meta.columns.sample_values` (by re-running `METADATA/10_populate_sample_values.sql`'s DO block) — the two pieces of meta.\* that go stale from data changes alone, with no DDL involved. `run_full_sync()` runs structural sync first (`drift_detector.run_drift_check()`), then this refresh, then an unconditional doc regen + incremental re-embed so changed sample values/row counts actually get picked up (§1.6) |
| Scheduler (interval-based auto-sync trigger) | `workers/scheduler.py` | ✅ | `APScheduler`-based long-running process (`python -m workers.scheduler`) that calls `sync_data_content.run_full_sync()` on an interval (`SYNC_INTERVAL_MINUTES` env var, default 60), firing once immediately on startup. Pure Python, OS-agnostic — no cron/Task Scheduler dependency, so the same process is meant to carry over unchanged to a future deployed/containerized environment. New pip dependency: `apscheduler` |
| Full-text search support | `METADATA/19_add_fulltext_search.sql` | ✅ | Adds `meta.document_embeddings.content_tsv` (`GENERATED ALWAYS AS (to_tsvector(...)) STORED`) + a GIN index. Confirmed backward-compatible: `reindex_embeddings.py`'s UPSERT uses an explicit column list, so the new generated column doesn't affect it. Enables `app/retrieval/hybrid_search.py`'s keyword leg |

## Retrieval layer (§2)

| Module | Location | Status | Notes |
|---|---|---|---|
| Document/chunk builder | `app/retrieval/document_builder.py` | ✅ | Moved from `RAG/metadata_documents.py` |
| Embedding generation + upsert | `workers/reindex_embeddings.py` | ✅ | Moved from `RAG/embedding_generator.py`. `main()` still does a full rebuild (embeds everything, but now also stamps `content_hash`); `incremental_reindex()` (used by `drift_detector.py`) only (re-)embeds documents whose `content_hash` changed and deletes rows for documents that no longer exist |
| Pure vector search | `app/retrieval/vector_search.py` | ✅ | Moved from `RAG/retriever.py`. `search_documents()` gained an optional `document_types` filter (backward-compatible, default `None`) so `hybrid_search.py` can scope the vector leg to `table`/`column` docs |
| Hybrid search (BM25 + vector, RRF) | `app/retrieval/hybrid_search.py` | ✅ | Dense leg reuses `vector_search.py`; sparse leg is a new `keyword_search()` against `meta.document_embeddings.content_tsv` (`METADATA/19_add_fulltext_search.sql` — generated `tsvector` column + GIN index). Combined via `reciprocal_rank_fusion()` (§2.1) |
| Cross-encoder re-ranking | `app/retrieval/rerank.py` | ✅ | `cross-encoder/ms-marco-MiniLM-L-6-v2` via `sentence_transformers.CrossEncoder` (no new pip dependency — already ships with `sentence-transformers`). Narrows `hybrid_search.py`'s top ~30 down to top 5-8 (§2.1) |
| Relationship graph / join-path BFS | `app/retrieval/relationship_graph.py` | ✅ | `build_graph()` (bidirectional adjacency from `meta.relationships`), `get_join_path(table_a, table_b)` (BFS shortest path), `get_related_tables(table_name)` (direct neighbors, used for relationship expansion). Verified multi-hop: `emi_payments → loans → customers` (§1.4, §2.1) |
| Confidence scoring + ambiguity-clarification path | `app/retrieval/confidence.py` | ✅ | `retrieve_context()` is the pipeline entry point: hybrid search → rerank → relationship expansion → `compute_confidence()` (blends sigmoid-squashed top rerank score with FK-graph connectivity ratio) → `needs_clarification()`. **Known calibration caveat**: `ms-marco-MiniLM-L-6-v2` was trained on passage-relevance data, so it scores lookup-style questions (e.g. "overdue EMI payments") much higher than aggregation-style ones (e.g. "which branch has the most defaulted loans") even when table selection is correct, since no single document *is* the answer to a GROUP BY question — verified this can push legitimate analytical questions into the `low`-confidence/clarification path under the current fixed thresholds (`HIGH_CONFIDENCE_THRESHOLD`/`MEDIUM_CONFIDENCE_THRESHOLD`/`AMBIGUITY_MARGIN` module constants in `confidence.py`). Left as tunable constants rather than hand-tuned against a handful of examples — revisit once real eval data exists (§2.2, §5) |

## Prompting (§3)

| Module | Location | Status | Notes |
|---|---|---|---|
| System prompt | `meta.prompt_versions` (DB) + `app/prompting/prompt_builder.py`'s `get_active_prompt()` | ✅ | §3.1's template was already seeded as DB data back in the Data Layer phase (`METADATA/14-15_*.sql`) — `prompt_builder.py` reads it (`WHERE prompt_name = ... AND is_active`) rather than duplicating the text in Python. Raises if no active row exists (fail fast, no silent fallback) |
| User prompt template | `app/prompting/templates/user_prompt.txt` | ✅ | §3.3's QUESTION/CONTEXT/OUTPUT-FORMAT skeleton, interpolated via plain Python `.format()` — no templating library added (none existed in the repo; only two interpolation points needed) |
| Prompt builder (context injection) | `app/prompting/prompt_builder.py` | ✅ | `assemble_context()` builds §3.2's context shape (tables/columns/join_paths/business_terms/query_patterns/confidence) by reusing `app/db/metadata_loader.py`'s existing loaders, filtered to the tables `retrieve_context()` selected. **Closed a real gap**: the seeded system prompt's rule 7 ("prefer a matching query_pattern example") and §3.2's `business_terms` section both assume retrieval fetched glossary/query_pattern docs, but `confidence.retrieve_context()` scopes hybrid search to `document_types=["table","column"]` only — `prompt_builder.py` adds two small extra `hybrid_search()` calls (`fetch_business_terms()`, `fetch_query_patterns()`) to actually populate those sections. `build_prompt()` does **not** short-circuit on `clarification_needed` — it still assembles a full prompt and surfaces the flag, leaving that policy decision to the caller (§3.2, §3.3) |

## SQL generation & validation (§4, §5)

| Module | Location | Status | Notes |
|---|---|---|---|
| LLM client | `app/llm/client.py` | ✅ | Google AI Studio / Gemini via the `google-genai` SDK (chosen over the legacy `google-generativeai` package). `call_llm()` takes `prompt_builder.build_prompt()`'s output directly — no DB access, no retrieval re-run. Uses Gemini's `response_schema` (constrains output to `SQLGenerationResponse` at generation time) + `temperature=0` (§3.4 determinism), plus one hand-rolled repair retry on parse/validation failure (not a generic retry library — no existing pattern for that in the repo, and it's a different concern than network transience). Live-tested: correct SQL for a lookup question, correct SQL for an aggregation question even when retrieval flagged low confidence (demonstrates why `build_prompt()`/`call_llm()` deliberately don't short-circuit on `clarification_needed`), and correct use of the `error: insufficient_context` escape hatch for an out-of-scope question. Does **not** do SQL validation, guardrails, cost estimation, or orchestration — those stay separate, unbuilt items below (§6.5, §8) |
| Structured-output schemas | `app/llm/schemas.py` | ✅ | One `SQLGenerationResponse` Pydantic model covers both branches of the seeded system prompt's contract (normal SQL response and the `{"error": "insufficient_context", ...}` shape) — Gemini's `response_schema` constrains the model to exactly one schema, so every field is optional and `is_error_response()` lets callers branch (§3.4) |
| SQL parser / hallucination check | `app/validation/sql_parser.py` | ⬜ | Stub — `sqlglot`/`pglast` (§5) |
| Guardrails (read-only, LIMIT, complexity, business rules) | `app/validation/guardrails.py` | ⬜ | Stub (§5) |
| Cost estimator (`EXPLAIN` check) | `app/validation/cost_estimator.py` | ⬜ | Stub (§5) |
| Full pipeline orchestration (retrieval → prompt → LLM → validate → execute) | — | ⬜ | Not started (§4) |

## API & app (§6)

| Module | Location | Status | Notes |
|---|---|---|---|
| FastAPI entrypoint | `app/main.py` | ⬜ | Stub |
| App settings | `app/config.py` | 🟡 | `GEMINI_API_KEY`/`GEMINI_MODEL` only so far (module-level `os.getenv()` constants, matching `workers/scheduler.py`'s existing convention — no settings-class abstraction introduced). Other app-wide settings (auth, etc.) not yet needed |
| `POST /api/v1/query` | `app/api/routes_query.py` | ⬜ | Stub |
| `POST /api/v1/feedback` | `app/api/routes_feedback.py` | ⬜ | Stub |
| `POST /api/v1/admin/reindex`, `/health`, `/metrics`, `/schema/search` | `app/api/routes_admin.py` | ⬜ | Stub |
| Auth (OAuth2/OIDC) + role-based schema visibility | — | ⬜ | Not started (§6.5) |
| Redis cache (embedding/context/LLM response) | — | ⬜ | Not started (§6.5, §9) |
| Streamlit UI | — | ⬜ | Not started (§6.2) |
| Docker/Kubernetes deployment | — | ⬜ | Not started (§6.5) |
| Monitoring (Prometheus/Grafana, structured logs) | — | ⬜ | Not started (§6.2) |

## Not yet mapped to a module (design-only, §9–§10)

- Async/parallel retrieval (`asyncio.gather` across keyword/vector/relationship lookups)
- Prompt/embedding/context caching (Redis)
- Streaming JSON responses to the UI
- SQL explanation, query-optimization suggestions, self-correction loop
- Conversational memory across turns
- Fine-tuning pipeline for the on-prem model tier
- Human-in-the-loop review queue for low-confidence queries
- Auto chart/dashboard recommendation
- Multi-database (`database_id`/`connection_id`) support
- Data lineage / column-level impact analysis

## What already exists and works standalone (pre-restructure)

- `test_connection.py` — root-level connectivity smoke test, unchanged
- `SQL/01-06_*.sql` — banking warehouse schema + dummy data + sample queries
- `METADATA/01-18_*.sql` — `meta` schema + population scripts (incl. query pattern few-shot bank, change-log triggers, prompt versioning, business rules, drift-detector support)

## Running the moved modules

`pip install -r requirements.txt` installs the pinned dependencies (added alongside the LLM client module —
previously only tracked in README prose). There's still no `pyproject.toml`/packaging, so run modules from
the repo root using `-m` so `app`/`workers` resolve as packages, e.g.:

```
python -m app.db.metadata_loader
python -m app.db.models
python -m workers.reindex_embeddings
python -m workers.generate_docs
python -m workers.drift_detector
python -m workers.sync_data_content
python -m workers.scheduler
python -m app.retrieval.vector_search
python -m app.retrieval.relationship_graph
python -m app.retrieval.hybrid_search
python -m app.retrieval.rerank
python -m app.retrieval.confidence
python -m app.prompting.prompt_builder
python -m app.llm.client
```
