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

---

## Technologies

- PostgreSQL
- pgvector (PostgreSQL extension, for vector embeddings)
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
│   ├── db/                    connection handling + metadata reads (implemented)
│   ├── retrieval/             document builder + vector search (implemented, semantic-only);
│   │                          hybrid_search.py, rerank.py, relationship_graph.py (stubs)
│   ├── prompting/              prompt_builder.py (stub)
│   ├── validation/            sql_parser.py, guardrails.py, cost_estimator.py (stubs)
│   ├── llm/                   client.py, schemas.py (stubs)
│   ├── api/                   routes_query.py, routes_feedback.py, routes_admin.py (stubs)
│   └── main.py, config.py     FastAPI entrypoint + settings (stubs)
├── workers/
│   ├── reindex_embeddings.py  embedding indexing job (implemented, full-rebuild only)
│   ├── generate_docs.py       auto-doc generation from information_schema (stub)
│   └── drift_detector.py      DDL drift → re-embed trigger (stub)
├── test_connection.py         standalone DB connectivity check (implemented)
└── docs/MODULES.md            module-by-module build status
```

## Prerequisites & Setup

To run the implemented scripts in this repo (`app/db/metadata_loader.py`, `workers/reindex_embeddings.py`, `app/retrieval/vector_search.py`, `test_connection.py`), you'll need:

- **PostgreSQL server**, with the **pgvector** extension enabled (used for storing/querying embeddings via the `vector` type and `<=>` distance operator)
- **Python 3.x** and **pip**
- Python packages installed via pip:
  - `psycopg2` (PostgreSQL driver)
  - `python-dotenv` (loads DB credentials from a `.env` file)
  - `sentence-transformers` (generates embeddings locally using `sentence-transformers/all-MiniLM-L6-v2`; pulls in `torch`/`transformers`)
- **Internet access on first run**, to download the `all-MiniLM-L6-v2` model from Hugging Face Hub
- A **`.env` file** in the project root (not included in the repo) defining:
  ```
  DB_HOST=localhost
  DB_PORT=5432
  DB_NAME=your_db_name
  DB_USER=your_db_user
  DB_PASSWORD=your_db_password
  ```

No LLM API key (OpenAI, Anthropic, etc.) is required for the code currently in this repo — embeddings are generated locally.

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

---

## Next Steps

- Query Pattern Metadata
- Automatic Metadata Refresh
- Change Log
- Text-to-SQL Integration

See [`docs/MODULES.md`](docs/MODULES.md) for the full module-by-module list of what's left to build toward the target architecture in [`enterprise-text-to-sql-architecture.md`](enterprise-text-to-sql-architecture.md).