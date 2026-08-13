"""
Drift detector: diffs the live `public` schema (information_schema) against
meta.tables/meta.columns, and if structural drift is found, syncs meta.*,
regenerates docs, and incrementally re-embeds — implementing the pipeline
in enterprise-text-to-sql-architecture.md §7's "Context Update Pipeline"
diagram:

    DDL change -> Drift Detector -> {Changed objects?}
        Yes -> Regenerate docs -> Update meta.tables/columns
            -> content_hash diff -> Re-embed changed chunks -> Upsert
        No  -> No-op

"Drift" here means structural change only: a table/column added or
dropped, or an existing column's data_type/nullable/is_pk/is_fk/
fk_ref_table/fk_ref_column changed. row_count_estimate is NOT treated as
drift (it changes constantly with normal data growth, not DDL) — but it's
baked into each table document's content, so a row-count change still
gets picked up and re-embedded automatically via content_hash diffing
the next time real drift triggers a sync, or via a direct
workers.generate_docs / reindex_embeddings run.

Critical design constraint: syncing meta.tables/meta.columns to match the
live schema must NEVER touch business_description/business_synonyms/
sample_values — those come from METADATA/07-10_*.sql, not from the
catalog, and a naive TRUNCATE+reinsert (like METADATA/03/04) would wipe
them. This module only INSERTs new rows (business content NULL, to be
filled later) or UPDATEs the structural columns on existing rows,
never touching the business columns.

See enterprise-text-to-sql-architecture.md §1.6, §7.
"""

from app.db.session import get_connection
from workers.generate_docs import generate_all_docs
from workers.reindex_embeddings import incremental_reindex

SCHEMA = "public"


def get_live_tables(connection, schema=SCHEMA):
    """Live table structure from information_schema/pg_class, keyed by table_name."""

    query = """
        SELECT
            t.table_name,
            t.table_type,
            COALESCE(c.reltuples::BIGINT, 0) AS row_count_estimate
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
        return {
            row[0]: {"object_type": row[1], "row_count_estimate": row[2]}
            for row in cursor.fetchall()
        }


def get_live_columns(connection, schema=SCHEMA):
    """Live column structure (incl. PK/FK) from information_schema/pg_constraint,
    keyed by (table_name, column_name)."""

    query = """
        SELECT
            c.table_name,
            c.column_name,
            c.data_type,
            (c.is_nullable = 'YES') AS nullable,
            COALESCE(pk.is_pk, FALSE) AS is_pk,
            COALESCE(fk.is_fk, FALSE) AS is_fk,
            fk.fk_ref_table,
            fk.fk_ref_column
        FROM information_schema.columns c
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
                ccu.column_name AS fk_ref_column,
                TRUE AS is_fk
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
        ORDER BY c.table_name, c.ordinal_position;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, {"schema": schema})
        return {
            (row[0], row[1]): {
                "data_type": row[2],
                "nullable": row[3],
                "is_pk": row[4],
                "is_fk": row[5],
                "fk_ref_table": row[6],
                "fk_ref_column": row[7],
            }
            for row in cursor.fetchall()
        }


def get_known_tables(connection, schema=SCHEMA):
    """meta.tables rows for schema, keyed by table_name."""

    query = "SELECT table_id, table_name, object_type FROM meta.tables WHERE schema_name = %s;"

    with connection.cursor() as cursor:
        cursor.execute(query, (schema,))
        return {
            row[1]: {"table_id": row[0], "object_type": row[2]}
            for row in cursor.fetchall()
        }


def get_known_columns(connection, schema=SCHEMA):
    """meta.columns rows (joined to meta.tables for the table name), keyed by
    (table_name, column_name)."""

    query = """
        SELECT mc.column_id, mt.table_name, mc.column_name, mc.data_type,
               mc.nullable, mc.is_pk, mc.is_fk, mc.fk_ref_table, mc.fk_ref_column
        FROM meta.columns mc
        JOIN meta.tables mt ON mt.table_id = mc.table_id
        WHERE mt.schema_name = %s;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (schema,))
        return {
            (row[1], row[2]): {
                "column_id": row[0],
                "data_type": row[3],
                "nullable": row[4],
                "is_pk": row[5],
                "is_fk": row[6],
                "fk_ref_table": row[7],
                "fk_ref_column": row[8],
            }
            for row in cursor.fetchall()
        }


def detect_table_drift(live_tables, known_tables):
    """New/dropped table names. object_type changes on existing tables are
    reported too, though they're essentially inert for this project."""

    new_tables = sorted(set(live_tables) - set(known_tables))
    dropped_tables = sorted(set(known_tables) - set(live_tables))
    changed_tables = sorted(
        name
        for name in set(live_tables) & set(known_tables)
        if live_tables[name]["object_type"] != known_tables[name]["object_type"]
    )

    return {"new": new_tables, "dropped": dropped_tables, "changed": changed_tables}


STRUCTURAL_COLUMN_FIELDS = ("data_type", "nullable", "is_pk", "is_fk", "fk_ref_table", "fk_ref_column")


def detect_column_drift(live_columns, known_columns):
    """New/dropped (table, column) pairs, plus existing columns whose
    structural fields (type/nullable/pk/fk) changed."""

    new_columns = sorted(set(live_columns) - set(known_columns))
    dropped_columns = sorted(set(known_columns) - set(live_columns))
    changed_columns = sorted(
        key
        for key in set(live_columns) & set(known_columns)
        if any(live_columns[key][field] != known_columns[key][field] for field in STRUCTURAL_COLUMN_FIELDS)
    )

    return {"new": new_columns, "dropped": dropped_columns, "changed": changed_columns}


def has_drift(table_drift, column_drift):
    return any(
        [
            table_drift["new"],
            table_drift["dropped"],
            table_drift["changed"],
            column_drift["new"],
            column_drift["dropped"],
            column_drift["changed"],
        ]
    )


def sync_schema(connection, schema, table_drift, column_drift, live_tables, live_columns, known_tables, known_columns):
    """Apply detected drift to meta.tables/meta.columns. INSERT/DELETE/UPDATE
    only touches structural fields — business_description/business_synonyms/
    sample_values on existing rows are never modified."""

    table_id_by_name = {name: info["table_id"] for name, info in known_tables.items()}

    with connection.cursor() as cursor:

        for table_name in table_drift["new"]:
            live = live_tables[table_name]
            cursor.execute(
                """
                INSERT INTO meta.tables (schema_name, table_name, object_type, row_count_estimate)
                VALUES (%s, %s, %s, %s)
                RETURNING table_id;
                """,
                (schema, table_name, live["object_type"], live["row_count_estimate"]),
            )
            table_id_by_name[table_name] = cursor.fetchone()[0]

        for table_name in table_drift["changed"]:
            live = live_tables[table_name]
            cursor.execute(
                "UPDATE meta.tables SET object_type = %s WHERE table_id = %s;",
                (live["object_type"], table_id_by_name[table_name]),
            )

        for table_name in table_drift["dropped"]:
            table_id = table_id_by_name[table_name]
            cursor.execute("DELETE FROM meta.columns WHERE table_id = %s;", (table_id,))
            cursor.execute("DELETE FROM meta.tables WHERE table_id = %s;", (table_id,))

        for table_name, column_name in column_drift["new"]:
            live = live_columns[(table_name, column_name)]
            cursor.execute(
                """
                INSERT INTO meta.columns
                    (table_id, column_name, data_type, nullable, is_pk, is_fk, fk_ref_table, fk_ref_column)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                """,
                (
                    table_id_by_name[table_name],
                    column_name,
                    live["data_type"],
                    live["nullable"],
                    live["is_pk"],
                    live["is_fk"],
                    live["fk_ref_table"],
                    live["fk_ref_column"],
                ),
            )

        for table_name, column_name in column_drift["changed"]:
            live = live_columns[(table_name, column_name)]
            column_id = known_columns[(table_name, column_name)]["column_id"]
            cursor.execute(
                """
                UPDATE meta.columns
                SET data_type = %s, nullable = %s, is_pk = %s, is_fk = %s,
                    fk_ref_table = %s, fk_ref_column = %s
                WHERE column_id = %s;
                """,
                (
                    live["data_type"],
                    live["nullable"],
                    live["is_pk"],
                    live["is_fk"],
                    live["fk_ref_table"],
                    live["fk_ref_column"],
                    column_id,
                ),
            )

        for table_name, column_name in column_drift["dropped"]:
            column_id = known_columns[(table_name, column_name)]["column_id"]
            cursor.execute("DELETE FROM meta.columns WHERE column_id = %s;", (column_id,))

    connection.commit()


def run_drift_check(connection, schema=SCHEMA):
    """Detect drift; if found, sync meta.*, regenerate docs, and incrementally
    re-embed. Returns a summary dict either way."""

    live_tables = get_live_tables(connection, schema)
    live_columns = get_live_columns(connection, schema)
    known_tables = get_known_tables(connection, schema)
    known_columns = get_known_columns(connection, schema)

    table_drift = detect_table_drift(live_tables, known_tables)
    column_drift = detect_column_drift(live_columns, known_columns)

    if not has_drift(table_drift, column_drift):
        return {"drift_detected": False, "table_drift": table_drift, "column_drift": column_drift}

    sync_schema(connection, schema, table_drift, column_drift, live_tables, live_columns, known_tables, known_columns)
    generate_all_docs(connection, schema)
    reindex_result = incremental_reindex(connection)

    return {
        "drift_detected": True,
        "table_drift": table_drift,
        "column_drift": column_drift,
        "reindex_result": reindex_result,
    }


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:
        print(f"Checking '{SCHEMA}' schema for drift against meta.tables/meta.columns...\n")

        result = run_drift_check(connection)

        if not result["drift_detected"]:
            print("No drift detected. No-op.")
            return

        table_drift = result["table_drift"]
        column_drift = result["column_drift"]

        print("Drift detected.")
        print("--------------------------------")
        print(f"Tables new:      {table_drift['new']}")
        print(f"Tables dropped:  {table_drift['dropped']}")
        print(f"Tables changed:  {table_drift['changed']}")
        print(f"Columns new:     {column_drift['new']}")
        print(f"Columns dropped: {column_drift['dropped']}")
        print(f"Columns changed: {column_drift['changed']}")

        print("\nmeta.tables/meta.columns synced (business content preserved).")
        print("Docs regenerated (docs/schema/*.md).")

        reindex_result = result["reindex_result"]
        print("\nIncremental re-embed:")
        print(f"  embedded:  {len(reindex_result['embedded'])} -> {reindex_result['embedded']}")
        print(f"  unchanged: {reindex_result['unchanged']}")
        print(f"  deleted:   {len(reindex_result['deleted'])} -> {reindex_result['deleted']}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
