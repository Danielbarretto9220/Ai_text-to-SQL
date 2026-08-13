-- ==========================================================
-- meta.change_log — versioning/audit trail (§1.6 of
-- enterprise-text-to-sql-architecture.md: "Every row in meta.tables/
-- meta.columns has updated_at; a trigger writes changes to
-- meta.change_log."). Not a manually-populated table — it fills
-- itself going forward as meta.tables/meta.columns rows change.
-- Safe to rerun (uses CREATE ... IF NOT EXISTS / CREATE OR REPLACE
-- throughout).
-- ==========================================================

CREATE TABLE IF NOT EXISTS meta.change_log (
    change_id     SERIAL PRIMARY KEY,
    schema_name   TEXT NOT NULL,
    table_name    TEXT NOT NULL,
    record_id     INT,
    operation     TEXT NOT NULL,
    changed_by    TEXT DEFAULT current_user,
    changed_at    TIMESTAMPTZ DEFAULT now(),
    old_data      JSONB,
    new_data      JSONB
);

-- meta.tables already has updated_at; meta.columns is missing it per
-- the architecture doc's requirement that both tables carry it.
ALTER TABLE meta.columns ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

-- Bumps updated_at on any UPDATE.
CREATE OR REPLACE FUNCTION meta.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Writes an audit row to meta.change_log for INSERT/UPDATE/DELETE.
-- Expects the row's PK column name as a trigger argument, since
-- meta.tables uses table_id and meta.columns uses column_id.
CREATE OR REPLACE FUNCTION meta.log_change()
RETURNS TRIGGER AS $$
DECLARE
    pk_column TEXT := TG_ARGV[0];
    rec_id    INT;
    old_json  JSONB;
    new_json  JSONB;
BEGIN
    old_json := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) ELSE NULL END;
    new_json := CASE WHEN TG_OP IN ('UPDATE', 'INSERT') THEN to_jsonb(NEW) ELSE NULL END;
    rec_id := COALESCE((new_json ->> pk_column), (old_json ->> pk_column))::INT;

    INSERT INTO meta.change_log (schema_name, table_name, record_id, operation, old_data, new_data)
    VALUES ('meta', TG_TABLE_NAME, rec_id, TG_OP, old_json, new_json);

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- meta.tables
CREATE OR REPLACE TRIGGER trg_tables_set_updated_at
    BEFORE UPDATE ON meta.tables
    FOR EACH ROW EXECUTE FUNCTION meta.set_updated_at();

CREATE OR REPLACE TRIGGER trg_tables_change_log
    AFTER INSERT OR UPDATE OR DELETE ON meta.tables
    FOR EACH ROW EXECUTE FUNCTION meta.log_change('table_id');

-- meta.columns
CREATE OR REPLACE TRIGGER trg_columns_set_updated_at
    BEFORE UPDATE ON meta.columns
    FOR EACH ROW EXECUTE FUNCTION meta.set_updated_at();

CREATE OR REPLACE TRIGGER trg_columns_change_log
    AFTER INSERT OR UPDATE OR DELETE ON meta.columns
    FOR EACH ROW EXECUTE FUNCTION meta.log_change('column_id');
