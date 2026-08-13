import os
import psycopg2
from dotenv import load_dotenv


load_dotenv()


def get_connection():
    """Create a connection to the PostgreSQL banking database."""

    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


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


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:

        tables = load_table_metadata(connection)
        columns = load_column_metadata(connection)
        relationships = load_relationship_metadata(connection)
        glossary = load_business_glossary(connection)

        print("Metadata loaded successfully.")
        print("--------------------------------")
        print(f"Tables:         {len(tables)}")
        print(f"Columns:        {len(columns)}")
        print(f"Relationships:  {len(relationships)}")
        print(f"Glossary terms: {len(glossary)}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()