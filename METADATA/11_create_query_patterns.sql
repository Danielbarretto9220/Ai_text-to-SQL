-- ==========================================================
-- meta.query_patterns — few-shot example bank (§1.2, §10 of
-- enterprise-text-to-sql-architecture.md). Maps a natural-language
-- question to a known-good SQL template, for retrieval-augmented
-- prompting and (later) the /api/v1/feedback few-shot loop.
-- Schema matches the architecture doc exactly.
-- ==========================================================

CREATE TABLE IF NOT EXISTS meta.query_patterns (
    pattern_id          SERIAL PRIMARY KEY,
    intent_description   TEXT,
    example_question      TEXT,
    sql_template           TEXT,
    tables_used             TEXT[]
);
