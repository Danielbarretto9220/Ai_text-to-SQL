-- ==========================================================
-- Populate meta.columns.sample_values
-- Dynamically pulls up to 5 real distinct values per column from
-- the actual source tables (requires dummy data to be loaded —
-- see SQL/02-05_*.sql). Generic/introspection-driven, so it stays
-- accurate as the underlying data changes. Safe to rerun.
-- ==========================================================

DO $$
DECLARE
    r RECORD;
    vals TEXT[];
BEGIN
    FOR r IN
        SELECT mc.column_id, mt.schema_name, mt.table_name, mc.column_name
        FROM meta.columns mc
        JOIN meta.tables mt ON mt.table_id = mc.table_id
    LOOP
        -- Sort in the column's native type first (so ints/dates sort
        -- numerically/chronologically, not lexicographically), then
        -- cast to text only for the final array.
        EXECUTE format(
            'SELECT ARRAY(SELECT v::text FROM (SELECT DISTINCT %I AS v FROM %I.%I WHERE %I IS NOT NULL ORDER BY %I LIMIT 5) s)',
            r.column_name, r.schema_name, r.table_name, r.column_name, r.column_name
        ) INTO vals;

        UPDATE meta.columns SET sample_values = vals WHERE column_id = r.column_id;
    END LOOP;
END $$;
