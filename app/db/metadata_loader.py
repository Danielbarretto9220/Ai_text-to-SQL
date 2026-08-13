from app.db.session import get_connection


def load_table_metadata(connection):
    """Load table-level metadata."""

    query = """
        SELECT
            table_id,
            schema_name,
            table_name,
            object_type,
            business_description,
            row_count_estimate
        FROM meta.tables
        ORDER BY table_name;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def load_column_metadata(connection):
    """Load column-level metadata."""

    query = """
        SELECT
            c.column_id,
            t.table_name,
            c.column_name,
            c.data_type,
            c.nullable,
            c.is_pk,
            c.is_fk,
            c.fk_ref_table,
            c.fk_ref_column,
            c.business_description,
            c.business_synonyms,
            c.sample_values
        FROM meta.columns c
        JOIN meta.tables t
            ON c.table_id = t.table_id
        ORDER BY t.table_name, c.column_name;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def load_relationship_metadata(connection):
    """Load table relationship metadata."""

    query = """
        SELECT
            relationship_id,
            from_table,
            from_column,
            to_table,
            to_column,
            relationship_type,
            verified,
            source
        FROM meta.relationships
        ORDER BY from_table, to_table;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def load_business_glossary(connection):
    """Load business glossary metadata."""

    query = """
        SELECT
            term_id,
            term,
            definition,
            maps_to_tables,
            maps_to_columns,
            synonyms
        FROM meta.business_glossary
        ORDER BY term;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def load_query_patterns(connection):
    """Load few-shot query pattern metadata."""

    query = """
        SELECT
            pattern_id,
            intent_description,
            example_question,
            sql_template,
            tables_used
        FROM meta.query_patterns
        ORDER BY pattern_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def load_business_rules(connection):
    """Load active guardrail business rules."""

    query = """
        SELECT
            rule_id,
            rule_name,
            description,
            rule_type,
            applies_to_tables,
            applies_to_columns,
            rule_logic,
            severity,
            is_active
        FROM meta.business_rules
        WHERE is_active
        ORDER BY rule_id;
    """

    with connection.cursor() as cursor:
        cursor.execute(query)
        return cursor.fetchall()


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:

        tables = load_table_metadata(connection)
        columns = load_column_metadata(connection)
        relationships = load_relationship_metadata(connection)
        glossary = load_business_glossary(connection)
        query_patterns = load_query_patterns(connection)
        business_rules = load_business_rules(connection)

        print("Metadata loaded successfully.")
        print("--------------------------------")
        print(f"Tables:         {len(tables)}")
        print(f"Columns:        {len(columns)}")
        print(f"Relationships:  {len(relationships)}")
        print(f"Glossary terms: {len(glossary)}")
        print(f"Query patterns: {len(query_patterns)}")
        print(f"Business rules: {len(business_rules)}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()