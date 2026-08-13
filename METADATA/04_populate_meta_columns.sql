-- ==========================================================
-- Populate meta.columns from PostgreSQL system catalog
-- Requires meta.tables to be populated first (03_populate_meta_tables.sql)
-- Safe to rerun
-- ==========================================================

-- Remove existing metadata (so the script can be rerun safely)
TRUNCATE TABLE meta.columns RESTART IDENTITY;

INSERT INTO meta.columns
(
    table_id,
    column_name,
    data_type,
    nullable,
    is_pk,
    is_fk,
    fk_ref_table,
    fk_ref_column
)
SELECT
    mt.table_id,
    c.column_name,
    c.data_type,
    (c.is_nullable = 'YES') AS nullable,
    COALESCE(pk.is_pk, FALSE) AS is_pk,
    COALESCE(fk.is_fk, FALSE) AS is_fk,
    fk.fk_ref_table,
    fk.fk_ref_column
FROM information_schema.columns c
JOIN meta.tables mt
       ON mt.schema_name = c.table_schema
      AND mt.table_name = c.table_name
LEFT JOIN (
    SELECT
        kcu.table_name,
        kcu.column_name,
        TRUE AS is_pk
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
           ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
    WHERE tc.constraint_type = 'PRIMARY KEY'
      AND tc.table_schema = 'public'
) pk
       ON pk.table_name = c.table_name
      AND pk.column_name = c.column_name
LEFT JOIN (
    SELECT
        kcu.table_name,
        kcu.column_name,
        TRUE AS is_fk,
        ccu.table_name AS fk_ref_table,
        ccu.column_name AS fk_ref_column
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
           ON tc.constraint_name = kcu.constraint_name
          AND tc.table_schema = kcu.table_schema
    JOIN information_schema.constraint_column_usage ccu
           ON tc.constraint_name = ccu.constraint_name
          AND tc.table_schema = ccu.table_schema
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND tc.table_schema = 'public'
) fk
       ON fk.table_name = c.table_name
      AND fk.column_name = c.column_name
WHERE c.table_schema = 'public'
ORDER BY mt.table_name, c.ordinal_position;
