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
│   ├── validation/            sql_parser.py, guardrails.py, cost_estimator.py (stubs)
│   ├── llm/                   client.py (Gemini via google-genai) + schemas.py (implemented)
│   ├── api/                   routes_query.py, routes_feedback.py, routes_admin.py (stubs)
│   └── main.py (stub), config.py (GEMINI_API_KEY/GEMINI_MODEL implemented)
├── workers/
│   ├── reindex_embeddings.py  embedding indexing job (implemented, full-rebuild only)
│   ├── generate_docs.py       auto-doc generation from information_schema (implemented)
│   ├── drift_detector.py      DDL drift → re-embed trigger (implemented)
│   ├── sync_data_content.py   row_count_estimate + sample_values refresh from live data (implemented)
│   └── scheduler.py           runs sync_data_content on an interval (implemented)
├── test_connection.py         standalone DB connectivity check (implemented)
└── docs/
    ├── MODULES.md              module-by-module build status
    └── schema/                 auto-generated per-table Markdown docs (generated, not hand-edited)
```

## Prerequisites & Setup

To run the implemented scripts in this repo (`app/db/metadata_loader.py`, `app/db/models.py`, `workers/reindex_embeddings.py`, `workers/generate_docs.py`, `workers/drift_detector.py`, `workers/sync_data_content.py`, `workers/scheduler.py`, `app/retrieval/vector_search.py`, `app/retrieval/hybrid_search.py`, `app/retrieval/rerank.py`, `app/retrieval/relationship_graph.py`, `app/retrieval/confidence.py`, `app/prompting/prompt_builder.py`, `app/llm/client.py`, `test_connection.py`), you'll need:

- **PostgreSQL server**, with the **pgvector** extension enabled (used for storing/querying embeddings via the `vector` type and `<=>` distance operator)
- **Python 3.x** and **pip**
- Python packages: `pip install -r requirements.txt` (pinned versions — `psycopg2-binary`, `python-dotenv`,
  `sentence-transformers`, `sqlalchemy`, `pgvector`, `apscheduler`, `google-genai`, `pydantic`)
  - `sentence-transformers` generates embeddings locally (`all-MiniLM-L6-v2`) and drives the reranker
    (`cross-encoder/ms-marco-MiniLM-L-6-v2`); pulls in `torch`/`transformers`
  - `pgvector` is the Python package (not the Postgres extension) — provides `pgvector.sqlalchemy.Vector`
  - `apscheduler` drives `workers/scheduler.py`'s interval-based auto-sync trigger
  - `google-genai` is the Gemini SDK used by `app/llm/client.py`; `pydantic` backs `app/llm/schemas.py`'s
    structured-output models
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
  ```
  `GEMINI_API_KEY` is from [Google AI Studio](https://aistudio.google.com/). `GEMINI_MODEL` is optional
  (defaults to `gemini-flash-latest`, a model-family alias that stays current without needing code changes
  as Google ships newer generations — a pinned model string like `gemini-2.5-flash` can and did go stale
  mid-project).

There's no `pyproject.toml`/packaging yet, so run the moved modules from the repo root with `-m` so `app`/`workers` resolve as packages, e.g. `python -m workers.reindex_embeddings`.

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

---

## Next Steps

- Text-to-SQL Integration (SQL validation/guardrails and API layers — see docs/MODULES.md)

See [`docs/MODULES.md`](docs/MODULES.md) for the full module-by-module list of what's left to build toward the target architecture in [`enterprise-text-to-sql-architecture.md`](enterprise-text-to-sql-architecture.md).