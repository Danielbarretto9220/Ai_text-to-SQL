-- ==========================================================
-- Metadata tables
-- Columns match what app/db/metadata_loader.py and
-- workers/reindex_embeddings.py actually read/write.
-- ==========================================================

CREATE TABLE meta.tables (
    table_id              SERIAL PRIMARY KEY,
    schema_name           TEXT NOT NULL,
    table_name            TEXT NOT NULL,
    object_type           TEXT,
    business_description  TEXT,
    row_count_estimate    BIGINT,
    updated_at            TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE meta.columns (
    column_id             SERIAL PRIMARY KEY,
    table_id              INT REFERENCES meta.tables(table_id),
    column_name           TEXT NOT NULL,
    data_type             TEXT,
    nullable              BOOLEAN,
    is_pk                 BOOLEAN DEFAULT FALSE,
    is_fk                 BOOLEAN DEFAULT FALSE,
    fk_ref_table          TEXT,
    fk_ref_column         TEXT,
    business_description  TEXT,
    business_synonyms     TEXT[],
    sample_values         TEXT[]
);

CREATE TABLE meta.relationships (
    relationship_id       SERIAL PRIMARY KEY,
    from_table            TEXT,
    from_column            TEXT,
    to_table               TEXT,
    to_column               TEXT,
    relationship_type      TEXT,
    verified                BOOLEAN DEFAULT FALSE,
    source                  TEXT
);

CREATE TABLE meta.business_glossary (
    term_id                SERIAL PRIMARY KEY,
    term                   TEXT NOT NULL,
    definition             TEXT,
    maps_to_tables         TEXT[],
    maps_to_columns        TEXT[],
    synonyms               TEXT[]
);

CREATE TABLE meta.document_embeddings (
    document_id            TEXT PRIMARY KEY,
    document_type          TEXT,
    content                 TEXT,
    embedding                VECTOR(384),
    metadata                 JSONB,
    created_at                TIMESTAMPTZ DEFAULT now()
);
