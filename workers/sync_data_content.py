"""
Data-content sync: refreshes meta.tables.row_count_estimate and
meta.columns.sample_values from the live `public` data — the two pieces
of meta.* that go stale purely from data changes (new rows, a new
distinct value appearing in a column), with no DDL involved at all.
This is a different concern from workers/drift_detector.py's structural
drift (schema shape), so it lives in its own module rather than being
folded into sync_schema().

run_full_sync() is the entry point meant to be called on a schedule
(see workers/scheduler.py): structural sync first, then data-content
refresh, then a final doc regen + incremental re-embed so the refreshed
content actually gets picked up.

See enterprise-text-to-sql-architecture.md §1.6, §7.
"""

import os

from app.db.session import get_connection
from workers.drift_detector import SCHEMA, get_known_tables, get_live_tables, run_drift_check
from workers.generate_docs import generate_all_docs
from workers.reindex_embeddings import incremental_reindex

SAMPLE_VALUES_SQL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "METADATA",
    "10_populate_sample_values.sql",
)


def refresh_row_counts(connection, schema=SCHEMA):
    """UPDATE meta.tables.row_count_estimate for every currently-known table
    (not just newly-created ones, unlike drift_detector.sync_schema)."""

    live_tables = get_live_tables(connection, schema)
    known_tables = get_known_tables(connection, schema)

    with connection.cursor() as cursor:
        for table_name, known in known_tables.items():
            live = live_tables.get(table_name)
            if live is None:
                continue
            cursor.execute(
                "UPDATE meta.tables SET row_count_estimate = %s WHERE table_id = %s;",
                (live["row_count_estimate"], known["table_id"]),
            )

    connection.commit()


def refresh_sample_values(connection):
    """Re-run METADATA/10_populate_sample_values.sql's DO block (read from
    that file, so the SQL has one source of truth) to pull fresh distinct
    values into meta.columns.sample_values for every known column."""

    with open(SAMPLE_VALUES_SQL_PATH, "r", encoding="utf-8") as sql_file:
        sql = sql_file.read()

    with connection.cursor() as cursor:
        cursor.execute(sql)

    connection.commit()


def run_full_sync(connection, schema=SCHEMA):
    """Structural sync, then data-content refresh, then a doc regen +
    incremental re-embed so the refreshed content is actually picked up.

    Order matters: structural sync must run first. If a column was just
    dropped live, a stale meta.columns row would make refresh_sample_values'
    dynamic SELECT DISTINCT <col> FROM <table> error on a column that no
    longer exists.
    """

    drift_result = run_drift_check(connection, schema)

    refresh_row_counts(connection, schema)
    refresh_sample_values(connection)

    generate_all_docs(connection, schema)
    reindex_result = incremental_reindex(connection)

    return {
        "drift_result": drift_result,
        "reindex_result": reindex_result,
    }


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:
        print("Running full metadata sync (structural + data-content)...\n")

        result = run_full_sync(connection)

        drift_result = result["drift_result"]
        reindex_result = result["reindex_result"]

        print(f"Structural drift detected: {drift_result['drift_detected']}")
        print("Row counts and sample values refreshed.")
        print("Docs regenerated (docs/schema/*.md).")

        print("\nIncremental re-embed:")
        print(f"  embedded:  {len(reindex_result['embedded'])} -> {reindex_result['embedded']}")
        print(f"  unchanged: {reindex_result['unchanged']}")
        print(f"  deleted:   {len(reindex_result['deleted'])} -> {reindex_result['deleted']}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
