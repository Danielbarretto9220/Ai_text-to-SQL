# Modules Required to Complete the Project

Status of every module called for by `enterprise-text-to-sql-architecture.md`, mapped to its location in the repo. Legend: ✅ implemented · 🟡 partial (works standalone, not to the doc's full spec) · ⬜ not started (stub file only, no logic).

## Data layer (§1)

| Module | Location | Status | Notes |
|---|---|---|---|
| `meta` schema (tables, columns, relationships, business_glossary) | `METADATA/01-10_*.sql` | ✅ | Populated tables per README "Current Progress" |
| `meta.document_embeddings` (pgvector) | `METADATA/*.sql` | ✅ | Written to by `workers/reindex_embeddings.py` |
| `meta.query_patterns` (few-shot bank) | — | ⬜ | No table/loader yet (§1.2, §10) |
| `meta.change_log` + `updated_at` trigger | — | ⬜ | Versioning/audit trail (§1.6) |
| `meta.prompt_versions` | — | ⬜ | Prompt template versioning (§3.4) |
| `meta.business_rules` | — | ⬜ | Backs `app/validation/guardrails.py` business-rule checks (§5) |
| ORM/typed models over `meta.*` | `app/db/models.py` | ⬜ | Stub |
| DB connection handling | `app/db/session.py` | ✅ | Consolidated from the old per-script `get_connection()` |
| Metadata reader | `app/db/metadata_loader.py` | ✅ | Moved from `RAG/metadata_loader.py` |
| Auto-generated Markdown docs from `information_schema` | `workers/generate_docs.py` | ⬜ | Stub (§1.7) |
| Drift detector (DDL change → re-embed) | `workers/drift_detector.py` | ⬜ | Stub (§1.6, §7) |

## Retrieval layer (§2)

| Module | Location | Status | Notes |
|---|---|---|---|
| Document/chunk builder | `app/retrieval/document_builder.py` | ✅ | Moved from `RAG/metadata_documents.py` |
| Embedding generation + upsert (full rebuild) | `workers/reindex_embeddings.py` | 🟡 | Moved from `RAG/embedding_generator.py`; not incremental (no `content_hash` diffing yet) |
| Pure vector search | `app/retrieval/vector_search.py` | ✅ | Moved from `RAG/retriever.py`; semantic-only today |
| Hybrid search (BM25 + vector, RRF) | `app/retrieval/hybrid_search.py` | ⬜ | Stub (§2.1) |
| Cross-encoder re-ranking | `app/retrieval/rerank.py` | ⬜ | Stub (§2.1) |
| Relationship graph / join-path BFS | `app/retrieval/relationship_graph.py` | ⬜ | Stub (§1.4, §2.1) |
| Confidence scoring + ambiguity-clarification path | — | ⬜ | Not started (§2.2, §5) |

## Prompting (§3)

| Module | Location | Status | Notes |
|---|---|---|---|
| System prompt template | `app/prompting/templates/` | ⬜ | Empty, template text from §3.1 not yet added |
| Prompt builder (context injection) | `app/prompting/prompt_builder.py` | ⬜ | Stub (§3.2, §3.3) |

## SQL generation & validation (§4, §5)

| Module | Location | Status | Notes |
|---|---|---|---|
| LLM client (provider-agnostic) | `app/llm/client.py` | ⬜ | Stub (§6.5, §8) |
| Structured-output schemas | `app/llm/schemas.py` | ⬜ | Stub (§3.4) |
| SQL parser / hallucination check | `app/validation/sql_parser.py` | ⬜ | Stub — `sqlglot`/`pglast` (§5) |
| Guardrails (read-only, LIMIT, complexity, business rules) | `app/validation/guardrails.py` | ⬜ | Stub (§5) |
| Cost estimator (`EXPLAIN` check) | `app/validation/cost_estimator.py` | ⬜ | Stub (§5) |
| Full pipeline orchestration (retrieval → prompt → LLM → validate → execute) | — | ⬜ | Not started (§4) |

## API & app (§6)

| Module | Location | Status | Notes |
|---|---|---|---|
| FastAPI entrypoint | `app/main.py` | ⬜ | Stub |
| App settings | `app/config.py` | ⬜ | Stub |
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
- `METADATA/01-10_*.sql` — `meta` schema + population scripts

## Running the moved modules

There's no `pyproject.toml`/packaging yet, so run modules from the repo root using `-m` so `app`/`workers` resolve as packages, e.g.:

```
python -m app.db.metadata_loader
python -m workers.reindex_embeddings
python -m app.retrieval.vector_search
```
