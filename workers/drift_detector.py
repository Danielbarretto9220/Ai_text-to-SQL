"""
Runs on warehouse DDL change: diffs information_schema against
meta.tables, flags drift, triggers generate_docs.py and incremental
re-embedding (content_hash diff) via reindex_embeddings.py.

Not yet implemented — see enterprise-text-to-sql-architecture.md §1.6, §7.
"""
