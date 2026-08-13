"""
Runs EXPLAIN (FORMAT JSON) on validated SQL before execution and rejects
queries whose estimated cost/rows exceed a configurable threshold.

EXPLAIN without ANALYZE never executes the query or touches data — it's
always safe/read-only, independent of whether the caller ever actually
runs the query (app/pipeline.py's execute_query()).

See enterprise-text-to-sql-architecture.md §5.
"""

from app.db.session import get_connection
from app.validation.sql_parser import parse_sql

DEFAULT_MAX_COST = 10000
DEFAULT_MAX_ROWS = 100000


def estimate_cost(connection, sql_text):
    """Runs EXPLAIN (FORMAT JSON) and returns (total_cost, plan_rows)
    from the root plan node."""

    with connection.cursor() as cursor:
        cursor.execute(f"EXPLAIN (FORMAT JSON) {sql_text}")
        plan = cursor.fetchone()[0][0]["Plan"]

    return plan["Total Cost"], plan["Plan Rows"]


def check_cost(connection, sql_text, max_cost=DEFAULT_MAX_COST, max_rows=DEFAULT_MAX_ROWS):
    """Rejects if the estimated cost or row count exceeds the threshold.
    Thresholds are generous defaults sized for this project's tiny
    dataset — real thresholds need tuning against real data volume, not
    guessed at."""

    total_cost, plan_rows = estimate_cost(connection, sql_text)

    errors = []
    if total_cost > max_cost:
        errors.append(f"Estimated cost {total_cost} exceeds threshold {max_cost}")
    if plan_rows > max_rows:
        errors.append(f"Estimated rows {plan_rows} exceeds threshold {max_rows}")

    return {"total_cost": total_cost, "plan_rows": plan_rows, "errors": errors}


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:
        sql_text = input("Enter SQL: ").strip()

        parsed, error = parse_sql(sql_text)
        if error:
            print(f"\nSyntax error: {error}")
            return

        result = check_cost(connection, sql_text)

        print(f"\nTotal cost: {result['total_cost']}")
        print(f"Plan rows: {result['plan_rows']}")
        print(f"Errors: {result['errors']}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
