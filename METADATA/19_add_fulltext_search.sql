-- ==========================================================
-- Add full-text search support to meta.document_embeddings
-- Enables the BM25/keyword leg of app/retrieval/hybrid_search.py's
-- Reciprocal Rank Fusion combine (architecture doc §2.1).
-- Safe to rerun.
-- ==========================================================

ALTER TABLE meta.document_embeddings
    ADD COLUMN IF NOT EXISTS content_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED;

CREATE INDEX IF NOT EXISTS idx_document_embeddings_content_tsv
    ON meta.document_embeddings USING GIN (content_tsv);
