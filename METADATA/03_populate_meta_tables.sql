-- ==========================================================
-- Populate meta.tables from PostgreSQL system catalog
-- ==========================================================

-- Remove existing metadata (so the script can be rerun safely)
TRUNCATE TABLE meta.tables RESTART IDENTITY CASCADE;

-- Insert current tables from the public schema
INSERT INTO meta.tables
(
    schema_name,
    table_name,
    object_type,
    row_count_estimate
)
SELECT
    t.table_schema,
    t.table_name,
    t.table_type,
    COALESCE(c.reltuples::BIGINT, 0) AS row_count_estimate
FROM information_schema.tables t
LEFT JOIN pg_class c
       ON c.relname = t.table_name
LEFT JOIN pg_namespace n
       ON n.oid = c.relnamespace
      AND n.nspname = t.table_schema
WHERE t.table_schema = 'public'
ORDER BY t.table_name;