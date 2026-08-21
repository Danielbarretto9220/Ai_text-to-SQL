"""
Parses generated SQL and resolves identifiers against meta.tables /
meta.columns to catch hallucinated tables/columns and unsupported joins.

Uses sqlglot (dialect="postgres") rather than pglast — pglast binds to
the real PostgreSQL C parser and needs native compilation, and this repo
already has a documented, painful Windows build history with pgvector
(PG 17.0-17.2 linker bug). sqlglot is pure Python and covers everything
needed here: parse, AST walk, transform (LIMIT injection in
guardrails.py), complexity counting.

See enterprise-text-to-sql-architecture.md §5.
"""

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.db.metadata_loader import get_connection, load_column_metadata, load_table_metadata
from app.retrieval.relationship_graph import build_graph


def parse_sql(sql_text):
    """Parse sql_text (postgres dialect). Returns (parsed, None) on
    success or (None, error_message) on a syntax error, rather than
    raising — callers decide what to do with a parse failure."""

    try:
        return sqlglot.parse_one(sql_text, read="postgres"), None
    except ParseError as exc:
        return None, str(exc)


def is_read_only(parsed):
    """True only for SELECT (including CTEs, which sqlglot parses as a
    Select with a "with" arg). Defense in depth — independent of the
    system prompt's own read-only instruction, never trusts the LLM
    followed it."""

    return isinstance(parsed, exp.Select)


def _known_schema(connection):
    """(known_tables: set[str], known_columns_by_table: dict[str, set[str]]),
    all lowercased, from meta.tables/meta.columns."""

    tables = load_table_metadata(connection)
    columns = load_column_metadata(connection)

    known_tables = {table_name.lower() for _, _, table_name, *_ in tables}

    known_columns_by_table = {}
    for _, table_name, column_name, *_ in columns:
        known_columns_by_table.setdefault(table_name.lower(), set()).add(column_name.lower())

    return known_tables, known_columns_by_table


def check_hallucinations(connection, parsed):
    """Walks Table/Column nodes, resolves aliases, and checks every
    referenced table/column against meta.tables/meta.columns. Returns a
    list of error strings (empty if clean)."""

    known_tables, known_columns_by_table = _known_schema(connection)

    errors = []

    alias_to_table = {}
    referenced_tables = set()

    for table_node in parsed.find_all(exp.Table):
        table_name = table_node.name.lower()
        referenced_tables.add(table_name)
        alias_to_table[table_name] = table_name
        alias_to_table[table_node.alias_or_name.lower()] = table_name

    for table_name in referenced_tables:
        if table_name not in known_tables:
            errors.append(f"Unknown table: {table_name}")

    valid_referenced_tables = referenced_tables & known_tables

    # SELECT-list aliases (e.g. COUNT(*) AS employee_count) are legal to
    # reference unqualified elsewhere in the query (ORDER BY employee_count,
    # HAVING employee_count > ...) without existing as a real schema column
    # anywhere — Postgres resolves these against the output list, not the
    # underlying tables. Found live: a Groq-generated `ORDER BY <alias>`
    # query was rejected as "unknown column" despite being correct SQL.
    known_aliases = {
        projection.alias.lower()
        for select_node in parsed.find_all(exp.Select)
        for projection in select_node.expressions
        if projection.alias
    }

    for column_node in parsed.find_all(exp.Column):
        column_name = column_node.name.lower()
        qualifier = column_node.table.lower() if column_node.table else None

        if qualifier:
            resolved_table = alias_to_table.get(qualifier)
            if resolved_table is None:
                errors.append(f"Unknown table alias/qualifier: {qualifier} (column {column_name})")
            elif resolved_table in known_tables and column_name not in known_columns_by_table.get(
                resolved_table, set()
            ):
                errors.append(f"Unknown column: {resolved_table}.{column_name}")
            # resolved_table not in known_tables is already reported as an unknown-table error above
        elif column_name in known_aliases:
            continue
        elif valid_referenced_tables:
            if len(valid_referenced_tables) == 1:
                only_table = next(iter(valid_referenced_tables))
                if column_name not in known_columns_by_table.get(only_table, set()):
                    errors.append(f"Unknown column: {column_name} (table {only_table})")
            else:
                found = any(
                    column_name in known_columns_by_table.get(t, set()) for t in valid_referenced_tables
                )
                if not found:
                    errors.append(
                        f"Unknown column: {column_name} "
                        f"(not found in any referenced table: {sorted(valid_referenced_tables)})"
                    )

    return errors


def check_joins(connection, parsed):
    """Every JOIN...ON condition must be backed by a real FK relationship
    in meta.relationships (either direction). Returns a list of error
    strings (empty if clean)."""

    graph = build_graph(connection)

    alias_to_table = {}
    for table_node in parsed.find_all(exp.Table):
        table_name = table_node.name.lower()
        alias_to_table[table_name] = table_name
        alias_to_table[table_node.alias_or_name.lower()] = table_name

    errors = []

    for join_node in parsed.find_all(exp.Join):
        on_condition = join_node.args.get("on")
        joined_table = join_node.this.name.lower() if isinstance(join_node.this, (exp.Table,)) else None

        if on_condition is None:
            errors.append(f"Join with no ON condition: {join_node.sql(dialect='postgres')}")
            continue

        equalities = list(on_condition.find_all(exp.EQ))
        if not equalities:
            errors.append(f"Join ON condition has no equality comparison: {on_condition.sql(dialect='postgres')}")
            continue

        supported = False

        for eq in equalities:
            left, right = eq.this, eq.expression
            if not (isinstance(left, exp.Column) and isinstance(right, exp.Column)):
                continue

            left_table = alias_to_table.get(left.table.lower()) if left.table else None
            right_table = alias_to_table.get(right.table.lower()) if right.table else None
            left_column, right_column = left.name.lower(), right.name.lower()

            if not left_table or not right_table:
                continue

            for edge in graph.get(left_table, []):
                edge_matches_forward = (
                    edge["to_table"] == right_table
                    and edge["from_column"].lower() == left_column
                    and edge["to_column"].lower() == right_column
                )
                edge_matches_reverse = (
                    edge["to_table"] == right_table
                    and edge["from_column"].lower() == right_column
                    and edge["to_column"].lower() == left_column
                )
                if edge_matches_forward or edge_matches_reverse:
                    supported = True
                    break

            if supported:
                break

        if not supported:
            errors.append(
                f"Unsupported join (no matching FK relationship in meta.relationships): "
                f"{'-> ' + joined_table if joined_table else ''} ON {on_condition.sql(dialect='postgres')}"
            )

    return errors


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:
        sql_text = input("Enter SQL to validate: ").strip()

        parsed, error = parse_sql(sql_text)

        if error:
            print(f"\nSyntax error: {error}")
            return

        print(f"\nRead-only: {is_read_only(parsed)}")

        hallucination_errors = check_hallucinations(connection, parsed)
        print(f"\nHallucination errors ({len(hallucination_errors)}):")
        for err in hallucination_errors:
            print(f"  - {err}")

        join_errors = check_joins(connection, parsed)
        print(f"\nJoin errors ({len(join_errors)}):")
        for err in join_errors:
            print(f"  - {err}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
