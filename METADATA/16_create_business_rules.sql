-- ==========================================================
-- meta.business_rules — backs app/validation/guardrails.py's
-- post-parse business-rule check (§5 of
-- enterprise-text-to-sql-architecture.md: "e.g. net_revenue must not
-- be summed with gross_revenue in the same query — rule table
-- checked post-parse"). No literal schema given in the architecture
-- doc for this table, so designed to be engine-interpretable rather
-- than prose-only: rule_logic is structured JSONB a future rules
-- engine can walk against the parsed SQL AST, not just a comment
-- for a human to read.
-- Safe to rerun.
-- ==========================================================

CREATE TABLE IF NOT EXISTS meta.business_rules (
    rule_id             SERIAL PRIMARY KEY,
    rule_name           TEXT NOT NULL UNIQUE,
    description         TEXT NOT NULL,
    rule_type           TEXT NOT NULL,
    applies_to_tables   TEXT[],
    applies_to_columns  TEXT[],
    rule_logic          JSONB NOT NULL,
    severity            TEXT NOT NULL DEFAULT 'error',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now(),

    CONSTRAINT chk_business_rules_type CHECK (
        rule_type IN (
            'forbidden_aggregation',
            'required_filter',
            'value_constraint',
            'join_constraint',
            'pii_exposure'
        )
    ),
    CONSTRAINT chk_business_rules_severity CHECK (severity IN ('error', 'warning'))
);

CREATE OR REPLACE TRIGGER trg_business_rules_set_updated_at
    BEFORE UPDATE ON meta.business_rules
    FOR EACH ROW EXECUTE FUNCTION meta.set_updated_at();

CREATE OR REPLACE TRIGGER trg_business_rules_change_log
    AFTER INSERT OR UPDATE OR DELETE ON meta.business_rules
    FOR EACH ROW EXECUTE FUNCTION meta.log_change('rule_id');
