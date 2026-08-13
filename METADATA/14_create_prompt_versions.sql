-- ==========================================================
-- meta.prompt_versions — versioned system prompt templates (§3.1,
-- §3.4 of enterprise-text-to-sql-architecture.md: "versioned prompt
-- templates stored in Postgres... so behavior changes are tracked").
-- Safe to rerun.
-- ==========================================================

CREATE TABLE IF NOT EXISTS meta.prompt_versions (
    version_id      SERIAL PRIMARY KEY,
    prompt_name     TEXT NOT NULL,
    version_number  INT NOT NULL,
    prompt_text     TEXT NOT NULL,
    is_active       BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT now(),
    notes           TEXT,
    UNIQUE (prompt_name, version_number)
);

-- Only one active version per prompt at a time.
CREATE UNIQUE INDEX IF NOT EXISTS uq_prompt_versions_one_active
    ON meta.prompt_versions (prompt_name)
    WHERE is_active;
