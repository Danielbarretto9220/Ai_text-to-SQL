-- ==========================================================
-- meta.query_log / meta.query_feedback — backs app/api/routes_query.py
-- and app/api/routes_feedback.py (§1.1: "Runtime query logs, feedback,
-- approved SQL -> PostgreSQL ... auditability, fine-tuning corpus,
-- few-shot example bank").
--
-- query_log is written once per POST /api/v1/query call. query_feedback
-- records a user verdict against a logged query, and can optionally be
-- promoted into meta.query_patterns (the existing few-shot bank),
-- closing §10's "feedback loop feeding a few-shot example bank" — that
-- promotion is a deliberate, explicit action (routes_feedback.py's
-- `promote` flag), never an automatic side effect of a thumbs-up.
--
-- Neither table gets the meta.set_updated_at()/log_change() triggers
-- used elsewhere: both are already themselves append-only logs, so
-- logging changes-to-the-log would be redundant.
--
-- Safe to rerun.
-- ==========================================================

CREATE TABLE IF NOT EXISTS meta.query_log (
    query_id                SERIAL PRIMARY KEY,
    question                 TEXT NOT NULL,
    generated_sql             TEXT,
    is_valid                  BOOLEAN,
    errors                    JSONB,
    warnings                  JSONB,
    tables_used                TEXT[],
    llm_confidence              TEXT,
    retrieval_confidence        NUMERIC,
    retrieval_label              TEXT,
    estimated_cost               NUMERIC,
    estimated_rows                BIGINT,
    retried_for_validation         BOOLEAN,
    prompt_version                 INT,
    latency_ms                     INT,
    created_at                     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS meta.query_feedback (
    feedback_id             SERIAL PRIMARY KEY,
    query_id                 INT REFERENCES meta.query_log(query_id) ON DELETE CASCADE,
    is_correct                BOOLEAN NOT NULL,
    corrected_sql              TEXT,
    comment                    TEXT,
    promoted_to_pattern_id      INT REFERENCES meta.query_patterns(pattern_id),
    created_at                  TIMESTAMPTZ DEFAULT now()
);
