"""
get_join_path(table_a, table_b): BFS over meta.relationships to give the
LLM a pre-computed join path instead of asking it to infer one. Also used
for relationship-expansion (pull in directly-joined tables post-retrieval).

See enterprise-text-to-sql-architecture.md §1.4, §2.1.
"""

from collections import deque

from app.db.metadata_loader import get_connection, load_relationship_metadata


def build_graph(connection):
    """Bidirectional adjacency dict built from meta.relationships:
    {table_name: [{"to_table", "from_column", "to_column",
    "relationship_type", "relationship_id"}, ...]}.

    Rows with a NULL from_table/to_table (both nullable in the schema) are
    skipped — they can't contribute a graph edge.
    """

    relationships = load_relationship_metadata(connection)

    graph = {}

    for row in relationships:
        (
            relationship_id,
            from_table,
            from_column,
            to_table,
            to_column,
            relationship_type,
            verified,
            source,
        ) = row

        if not from_table or not to_table:
            continue

        graph.setdefault(from_table, []).append(
            {
                "to_table": to_table,
                "from_column": from_column,
                "to_column": to_column,
                "relationship_type": relationship_type,
                "relationship_id": relationship_id,
            }
        )
        graph.setdefault(to_table, []).append(
            {
                "to_table": from_table,
                "from_column": to_column,
                "to_column": from_column,
                "relationship_type": relationship_type,
                "relationship_id": relationship_id,
            }
        )

    return graph


def get_related_tables(connection, table_name):
    """Direct neighbors of table_name (used for relationship expansion —
    pulling in directly-joined tables even if they didn't rank highly)."""

    graph = build_graph(connection)

    return sorted({edge["to_table"] for edge in graph.get(table_name, [])})


def get_join_path(connection, table_a, table_b):
    """BFS shortest join path from table_a to table_b.

    Returns an ordered list of hop dicts ({"from_table", "from_column",
    "to_table", "to_column", "relationship_type"}), [] if table_a ==
    table_b, or None if no path exists (disconnected, or either table
    isn't in the graph at all).
    """

    if table_a == table_b:
        return []

    graph = build_graph(connection)

    if table_a not in graph or table_b not in graph:
        return None

    visited = {table_a}
    queue = deque([(table_a, [])])

    while queue:
        current_table, path_so_far = queue.popleft()

        for edge in graph.get(current_table, []):
            next_table = edge["to_table"]

            if next_table in visited:
                continue

            hop = {
                "from_table": current_table,
                "from_column": edge["from_column"],
                "to_table": next_table,
                "to_column": edge["to_column"],
                "relationship_type": edge["relationship_type"],
            }

            new_path = path_so_far + [hop]

            if next_table == table_b:
                return new_path

            visited.add(next_table)
            queue.append((next_table, new_path))

    return None


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:
        table_a = input("Table A: ").strip()
        table_b = input("Table B: ").strip()

        path = get_join_path(connection, table_a, table_b)

        print("\n" + "=" * 70)
        print(f"JOIN PATH: {table_a} -> {table_b}")
        print("=" * 70)

        if path is None:
            print("No path found (disconnected, or unknown table name).")
        elif not path:
            print("Same table — no join needed.")
        else:
            for hop in path:
                print(
                    f"  {hop['from_table']}.{hop['from_column']} -> "
                    f"{hop['to_table']}.{hop['to_column']} "
                    f"({hop['relationship_type']})"
                )

        related = get_related_tables(connection, table_a)
        print(f"\nTables directly related to '{table_a}': {related}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
