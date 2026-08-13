"""
Auto-generates per-table Markdown documentation for the `public` (banking
warehouse) schema.

Two-tier design so structure never drifts even if business enrichment lags
(§1.7): every structural fact (columns, types, nullability, PK/FK,
row estimate, `COMMENT ON` text) is introspected fresh from
`information_schema` / `pg_constraint` / `pg_description` on every run —
never read from meta.*, so it can't go stale relative to the real schema.
Business content (descriptions, synonyms, sample values, glossary terms)
is merged in from meta.tables/meta.columns/meta.business_glossary as a
second, best-effort layer that's simply omitted if meta.* hasn't been
populated for a table yet.

Unlike the architecture doc's literal description ("SMEs then enrich [the
generated Markdown]"), this repo's enrichment path is upstream of this
script: business content lives in METADATA/07-10_*.sql and flows into
meta.tables/meta.columns, and this script is a read-only downstream
projection of both the catalog and meta.*. Generated files are
regenerated whole on every run (full rebuild, matching
workers/reindex_embeddings.py's current maturity level) — don't hand-edit
them; edit the source (METADATA/*.sql or the live DDL) instead.

Output: docs/schema/<table_name>.md, plus a docs/schema/README.md index.

See enterprise-text-to-sql-architecture.md §1.7.
"""

import os

from app.db.session import get_connection

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "schema")


def get_tables(connection, schema="public"):
    """List base tables/views in a schema, with live row-count estimates."""

    query = """
        SELECT
            t.table_name,
            t.table_type,
            COALESCE(c.reltuples::BIGINT, 0) AS row_count_estimate,
            obj_description(c.oid, 'pg_class') AS table_comment
        FROM information_schema.tables t
        LEFT JOIN pg_class c
               ON c.relname = t.table_name
        LEFT JOIN pg_namespace n
               ON n.oid = c.relnamespace
              AND n.nspname = t.table_schema
        WHERE t.table_schema = %s
        ORDER BY t.table_name;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (schema,))
        return cursor.fetchall()


def get_columns(connection, schema, table_name):
    """Introspect columns + PK/FK flags for one table, fresh from the catalog."""

    query = """
        SELECT
            c.column_name,
            c.data_type,
            c.is_nullable,
            c.column_default,
            COALESCE(pk.is_pk, FALSE) AS is_pk,
            fk.fk_ref_table,
            fk.fk_ref_column,
            col_description(cls.oid, c.ordinal_position) AS column_comment
        FROM information_schema.columns c
        LEFT JOIN pg_class cls
               ON cls.relname = c.table_name
        LEFT JOIN pg_namespace ns
               ON ns.oid = cls.relnamespace
              AND ns.nspname = c.table_schema
        LEFT JOIN (
            SELECT kcu.table_name, kcu.column_name, TRUE AS is_pk
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                   ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = %(schema)s
        ) pk
               ON pk.table_name = c.table_name
              AND pk.column_name = c.column_name
        LEFT JOIN (
            SELECT
                kcu.table_name, kcu.column_name,
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
              AND tc.table_schema = %(schema)s
        ) fk
               ON fk.table_name = c.table_name
              AND fk.column_name = c.column_name
        WHERE c.table_schema = %(schema)s
          AND c.table_name = %(table_name)s
        ORDER BY c.ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, {"schema": schema, "table_name": table_name})
        return cursor.fetchall()


def get_incoming_foreign_keys(connection, schema, table_name):
    """Other tables' columns that reference this table (the 'referenced by' side)."""

    query = """
        SELECT
            tc.table_name AS from_table,
            kcu.column_name AS from_column,
            ccu.column_name AS to_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
               ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
               ON tc.constraint_name = ccu.constraint_name
              AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = %(schema)s
          AND ccu.table_name = %(table_name)s
        ORDER BY tc.table_name, kcu.column_name;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, {"schema": schema, "table_name": table_name})
        return cursor.fetchall()


def get_meta_table_context(connection, schema, table_name):
    """Best-effort business enrichment for a table from meta.tables. None if not present."""

    query = """
        SELECT business_description
        FROM meta.tables
        WHERE schema_name = %s AND table_name = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (schema, table_name))
        row = cursor.fetchone()
        return row[0] if row else None


def get_meta_column_context(connection, table_name):
    """Best-effort business enrichment per column from meta.columns. Empty dict if not present."""

    query = """
        SELECT c.column_name, c.business_description, c.business_synonyms, c.sample_values
        FROM meta.columns c
        JOIN meta.tables t ON t.table_id = c.table_id
        WHERE t.table_name = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (table_name,))
        return {
            row[0]: {"description": row[1], "synonyms": row[2] or [], "samples": row[3] or []}
            for row in cursor.fetchall()
        }


def get_glossary_terms_for_table(connection, table_name):
    """Business glossary terms whose maps_to_tables includes this table."""

    query = """
        SELECT term, definition
        FROM meta.business_glossary
        WHERE %s = ANY(maps_to_tables)
        ORDER BY term;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (table_name,))
        return cursor.fetchall()


def render_table_markdown(
    schema,
    table_name,
    table_type,
    row_count_estimate,
    table_comment,
    meta_description,
    columns,
    incoming_fks,
    glossary_terms,
    meta_columns,
):
    """Build the Markdown document for one table."""

    lines = [
        f"# {table_name}",
        "",
        "> Auto-generated by `workers/generate_docs.py` from `information_schema`/"
        "`pg_constraint`/`pg_description` + `meta.*`. Do not hand-edit — structural "
        "changes come from the live schema, business content from `METADATA/07-10_*.sql`. "
        "Re-run the generator to refresh.",
        "",
        f"**Schema:** {schema}  ",
        f"**Type:** {table_type}  ",
        f"**Estimated Rows:** {row_count_estimate}",
        "",
        "**Description:** "
        + (table_comment or meta_description or "_Not yet documented._"),
        "",
        "## Columns",
        "",
        "| Column | Type | Nullable | PK | FK | References | Description | Sample Values |",
        "|---|---|---|---|---|---|---|---|",
    ]

    for (
        column_name,
        data_type,
        is_nullable,
        _column_default,
        is_pk,
        fk_ref_table,
        fk_ref_column,
        column_comment,
    ) in columns:
        pk_mark = "PK" if is_pk else ""
        fk_mark = "FK" if fk_ref_table else ""
        references = f"{fk_ref_table}.{fk_ref_column}" if fk_ref_table else ""

        enrichment = meta_columns.get(column_name, {})
        description = column_comment or enrichment.get("description") or ""
        samples = enrichment.get("samples") or []
        samples_text = ", ".join(str(v) for v in samples[:5])

        lines.append(
            f"| {column_name} | {data_type} | {is_nullable} | {pk_mark} | {fk_mark} "
            f"| {references} | {description} | {samples_text} |"
        )

    lines += ["", "## Relationships", ""]

    outgoing = [
        (c[0], c[5], c[6]) for c in columns if c[5]
    ]  # column_name, fk_ref_table, fk_ref_column

    if outgoing or incoming_fks:
        if outgoing:
            lines.append("**References:**")
            for column_name, ref_table, ref_column in outgoing:
                lines.append(f"- `{table_name}.{column_name}` → `{ref_table}.{ref_column}`")
            lines.append("")
        if incoming_fks:
            lines.append("**Referenced by:**")
            for from_table, from_column, to_column in incoming_fks:
                lines.append(f"- `{from_table}.{from_column}` → `{table_name}.{to_column}`")
            lines.append("")
    else:
        lines.append("_No foreign key relationships._")
        lines.append("")

    lines += ["## Business Glossary Terms", ""]

    if glossary_terms:
        for term, definition in glossary_terms:
            lines.append(f"- **{term}**: {definition}")
    else:
        lines.append("_No glossary terms reference this table._")

    lines.append("")

    return "\n".join(lines)


def render_index_markdown(tables):
    """Build docs/schema/README.md linking to every generated table doc."""

    lines = [
        "# Schema Documentation",
        "",
        "> Auto-generated by `workers/generate_docs.py`. One file per table in the "
        "`public` (banking warehouse) schema.",
        "",
        "| Table | Type | Estimated Rows | Description |",
        "|---|---|---|---|",
    ]

    for table_name, table_type, row_count_estimate, description in tables:
        short_description = (description or "_Not yet documented._").split("\n")[0]
        lines.append(
            f"| [{table_name}]({table_name}.md) | {table_type} | {row_count_estimate} "
            f"| {short_description} |"
        )

    lines.append("")

    return "\n".join(lines)


def generate_all_docs(connection, schema="public", output_dir=OUTPUT_DIR):
    """Generate and write a Markdown doc for every table in schema, plus an
    index. Also removes stale per-table .md files left over from a table
    that no longer exists (e.g. dropped by a drift event)."""

    os.makedirs(output_dir, exist_ok=True)

    tables = get_tables(connection, schema)
    current_table_names = {table_name for table_name, *_ in tables}

    for existing_file in os.listdir(output_dir):
        if not existing_file.endswith(".md") or existing_file == "README.md":
            continue
        table_name = existing_file[: -len(".md")]
        if table_name not in current_table_names:
            os.remove(os.path.join(output_dir, existing_file))

    index_rows = []

    for table_name, table_type, row_count_estimate, table_comment in tables:

        columns = get_columns(connection, schema, table_name)
        incoming_fks = get_incoming_foreign_keys(connection, schema, table_name)
        meta_description = get_meta_table_context(connection, schema, table_name)
        meta_columns = get_meta_column_context(connection, table_name)
        glossary_terms = get_glossary_terms_for_table(connection, table_name)

        markdown = render_table_markdown(
            schema,
            table_name,
            table_type,
            row_count_estimate,
            table_comment,
            meta_description,
            columns,
            incoming_fks,
            glossary_terms,
            meta_columns,
        )

        file_path = os.path.join(output_dir, f"{table_name}.md")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        index_rows.append((table_name, table_type, row_count_estimate, table_comment or meta_description))

    index_markdown = render_index_markdown(index_rows)
    with open(os.path.join(output_dir, "README.md"), "w", encoding="utf-8") as f:
        f.write(index_markdown)

    return [table_name for table_name, *_ in index_rows]


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:
        print("Generating schema documentation...")

        table_names = generate_all_docs(connection)

        print("Docs generated successfully.")
        print("--------------------------------")
        print(f"Tables documented: {len(table_names)}")
        for table_name in table_names:
            print(f"  - docs/schema/{table_name}.md")
        print("  - docs/schema/README.md (index)")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
