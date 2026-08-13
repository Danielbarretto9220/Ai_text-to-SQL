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
authoritative, up-to-date status table (✅/🟡/⬜) of every module against the architecture doc. Most files
under `app/` are still docstring-only stubs; only a subset is real. Don't assume a file has logic just
because it exists.

## Current implementation status (see docs/MODULES.md for details)

**Implemented (real logic):**
- `METADATA/01-18_*.sql` — the whole `meta` schema and its population (tables, columns, relationships,
  business glossary, query patterns, change log, prompt versions, business rules, drift support)
- `app/db/session.py`, `app/db/metadata_loader.py`, `app/db/models.py` (SQLAlchemy ORM over `meta.*`)
- `app/retrieval/` — `document_builder.py`, `vector_search.py`, `hybrid_search.py`, `rerank.py`,
  `relationship_graph.py`, `confidence.py` (the full retrieval pipeline — see below)
- `workers/reindex_embeddings.py`, `workers/generate_docs.py`, `workers/drift_detector.py`,
  `workers/sync_data_content.py`, `workers/scheduler.py`

**Stubs (docstring only, no logic yet)** — implementing one of these means writing the first real code
for that piece, guided by the architecture doc section referenced in its docstring:
- `app/prompting/prompt_builder.py`, `app/prompting/templates/`
- `app/llm/client.py`, `app/llm/schemas.py`
- `app/validation/sql_parser.py`, `guardrails.py`, `cost_estimator.py`
- `app/main.py`, `app/config.py`, `app/api/routes_*.py`

When picking up a stub, read its docstring first (it cites the exact architecture-doc section) and read
that section before writing code.

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
python test_connection.py     # standalone DB connectivity smoke test, run directly (not -m)
```

There is no test suite yet (`tests/` is an empty package) and no lint/format config in the repo.

### Environment

Requires a local `.env` (gitignored) with `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` — a
PostgreSQL instance with the **pgvector** extension enabled. No LLM API key is needed yet; embeddings are
generated locally via `sentence-transformers/all-MiniLM-L6-v2` (384-dim vectors), which pulls in
`torch`/`transformers` and needs internet access on first run to pull the model from Hugging Face.

Key packages: `psycopg2`, `python-dotenv`, `sqlalchemy` (2.0), `pgvector` (Python package, for
`pgvector.sqlalchemy.Vector`), `sentence-transformers` (also provides `CrossEncoder`, used by
`app/retrieval/rerank.py` — no separate reranking package needed), `apscheduler` (drives
`workers/scheduler.py`). pgvector on Windows needs PG **17.3+** (17.0–17.2 has a Windows linker bug that
breaks building the extension from source).

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

**Target end-to-end pipeline** (retrieval is done; prompting onward is not yet wired — see architecture doc
§4 for the full diagram): question → `retrieve_context()` → prompt construction (versioned templates from
`meta.prompt_versions`) → LLM call (structured JSON output) → SQL validation (hallucination check against
`meta.tables`/`meta.columns`, join check against `meta.relationships`, read-only enforcement, LIMIT
injection, business-rule check against `meta.business_rules`, EXPLAIN cost check) → execution against a
read-only replica → result formatting.

## Working conventions in this repo

- Follow the existing code style: heavy docstrings explaining *why* and pointing at the relevant
  architecture-doc section, generous blank lines between logical blocks, `print()`-based progress logging
  in scripts (no logging framework yet).
- Ask before adding new dependencies or diverging from the existing code/architecture pattern, even when
  you're confident in the alternative — this project follows the architecture doc closely and departures
  should be a deliberate, discussed choice.
- `docs/schema/*.md` and `docs/MODULES.md`'s status column are generated/status-tracking artifacts —
  regenerate `docs/schema/*.md` via `workers/generate_docs.py` rather than hand-editing, and update
  `docs/MODULES.md` when a stub becomes implemented.
