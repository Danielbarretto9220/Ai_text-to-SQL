-- ==========================================================
-- Populate meta.relationships from PostgreSQL Foreign Keys
-- Safe to rerun
-- ==========================================================

-- Remove existing relationships
TRUNCATE TABLE meta.relationships RESTART IDENTITY;

INSERT INTO meta.relationships
(
    from_table,
    from_column,
    to_table,
    to_column,
    relationship_type,
    verified,
    source
)

SELECT

    tc.table_name AS from_table,

    kcu.column_name AS from_column,

    ccu.table_name AS to_table,

    ccu.column_name AS to_column,

    'Foreign Key (1:N)' AS relationship_type,

    TRUE AS verified,

    'information_schema' AS source

FROM information_schema.table_constraints tc

JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema

JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
   AND tc.table_schema = ccu.table_schema

WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'

ORDER BY
    tc.table_name,
    kcu.column_name;