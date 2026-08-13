-- ==========================================================
-- Schema support for workers/drift_detector.py (§1.6, §7 of
-- enterprise-text-to-sql-architecture.md).
--
-- 1. meta.document_embeddings.content_hash — lets the drift detector
--    (and reindex_embeddings.incremental_reindex) tell which RAG
--    documents actually changed, so only those get re-embedded
--    instead of a full rebuild every time (§1.6: "only chunks whose
--    hash changed are re-embedded").
-- 2. Unique constraints on meta.tables(schema_name, table_name) and
--    meta.columns(table_id, column_name) — needed for the drift
--    detector to do a real UPSERT (INSERT ... ON CONFLICT) instead of
--    TRUNCATE+reinsert, which would destroy the business_description/
--    business_synonyms/sample_values populated by METADATA/07-10.
--
-- Safe to rerun.
-- ==========================================================

ALTER TABLE meta.document_embeddings ADD COLUMN IF NOT EXISTS content_hash TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_meta_tables_schema_table'
    ) THEN
        ALTER TABLE meta.tables
            ADD CONSTRAINT uq_meta_tables_schema_table UNIQUE (schema_name, table_name);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'uq_meta_columns_table_column'
    ) THEN
        ALTER TABLE meta.columns
            ADD CONSTRAINT uq_meta_columns_table_column UNIQUE (table_id, column_name);
    END IF;
END $$;
