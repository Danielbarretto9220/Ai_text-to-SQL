"""
Convert PostgreSQL metadata into searchable RAG documents.

Source:
    app/db/metadata_loader.py

The documents created here contain:
    - Table metadata
    - Column metadata
    - Relationship metadata
    - Business glossary metadata
    - Query pattern metadata (few-shot examples)
"""

from app.db.metadata_loader import (
    get_connection,
    load_table_metadata,
    load_column_metadata,
    load_relationship_metadata,
    load_business_glossary,
    load_query_patterns,
)


def build_table_documents(tables):
    """Convert table metadata rows into searchable documents."""

    documents = []

    for row in tables:
        (
            table_id,
            schema_name,
            table_name,
            object_type,
            business_description,
            row_count_estimate,
        ) = row

        text = f"""
TABLE
Schema: {schema_name}
Table: {table_name}
Object Type: {object_type}
Business Description: {business_description or "Not available"}
Estimated Rows: {row_count_estimate}
""".strip()

        documents.append(
            {
                "document_type": "table",
                "table_name": table_name,
                "content": text,
                "metadata": {
                    "table_id": table_id,
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "object_type": object_type,
                },
            }
        )

    return documents


def build_column_documents(columns):
    """Convert column metadata rows into searchable documents."""

    documents = []

    for row in columns:
        (
            column_id,
            table_name,
            column_name,
            data_type,
            nullable,
            is_pk,
            is_fk,
            fk_ref_table,
            fk_ref_column,
            business_description,
            business_synonyms,
            sample_values,
        ) = row

        synonyms = ", ".join(business_synonyms or [])
        samples = ", ".join(str(value) for value in (sample_values or []))

        text = f"""
COLUMN
Table: {table_name}
Column: {column_name}
Data Type: {data_type}
Nullable: {nullable}
Primary Key: {is_pk}
Foreign Key: {is_fk}
Referenced Table: {fk_ref_table or "None"}
Referenced Column: {fk_ref_column or "None"}
Business Description: {business_description or "Not available"}
Business Synonyms: {synonyms or "None"}
Sample Values: {samples or "None"}
""".strip()

        documents.append(
            {
                "document_type": "column",
                "table_name": table_name,
                "column_name": column_name,
                "content": text,
                "metadata": {
                    "column_id": column_id,
                    "table_name": table_name,
                    "column_name": column_name,
                    "data_type": data_type,
                    "is_pk": is_pk,
                    "is_fk": is_fk,
                },
            }
        )

    return documents


def build_relationship_documents(relationships):
    """Convert relationship metadata into searchable documents."""

    documents = []

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

        text = f"""
RELATIONSHIP
From Table: {from_table}
From Column: {from_column}
To Table: {to_table}
To Column: {to_column}
Relationship Type: {relationship_type}
Verified: {verified}
Source: {source or "Not available"}
""".strip()

        documents.append(
            {
                "document_type": "relationship",
                "table_name": from_table,
                "content": text,
                "metadata": {
                    "relationship_id": relationship_id,
                    "from_table": from_table,
                    "from_column": from_column,
                    "to_table": to_table,
                    "to_column": to_column,
                    "relationship_type": relationship_type,
                    "verified": verified,
                },
            }
        )

    return documents


def build_glossary_documents(glossary):
    """Convert business glossary entries into searchable documents."""

    documents = []

    for row in glossary:
        (
            term_id,
            term,
            definition,
            maps_to_tables,
            maps_to_columns,
            synonyms,
        ) = row

        mapped_tables = ", ".join(maps_to_tables or [])
        mapped_columns = ", ".join(maps_to_columns or [])
        glossary_synonyms = ", ".join(synonyms or [])

        text = f"""
BUSINESS GLOSSARY
Term: {term}
Definition: {definition}
Maps To Tables: {mapped_tables or "None"}
Maps To Columns: {mapped_columns or "None"}
Synonyms: {glossary_synonyms or "None"}
""".strip()

        documents.append(
            {
                "document_type": "glossary",
                "term": term,
                "content": text,
                "metadata": {
                    "term_id": term_id,
                    "term": term,
                },
            }
        )

    return documents


def build_query_pattern_documents(query_patterns):
    """Convert few-shot query pattern rows into searchable documents."""

    documents = []

    for row in query_patterns:
        (
            pattern_id,
            intent_description,
            example_question,
            sql_template,
            tables_used,
        ) = row

        tables = ", ".join(tables_used or [])

        text = f"""
QUERY PATTERN
Intent: {intent_description}
Example Question: {example_question}
SQL Template:
{sql_template}
Tables Used: {tables or "None"}
""".strip()

        documents.append(
            {
                "document_type": "query_pattern",
                "content": text,
                "metadata": {
                    "pattern_id": pattern_id,
                    "tables_used": tables_used,
                },
            }
        )

    return documents


def build_all_documents(connection):
    """Load all metadata and convert it into RAG documents."""

    tables = load_table_metadata(connection)
    columns = load_column_metadata(connection)
    relationships = load_relationship_metadata(connection)
    glossary = load_business_glossary(connection)
    query_patterns = load_query_patterns(connection)

    documents = []

    documents.extend(build_table_documents(tables))
    documents.extend(build_column_documents(columns))
    documents.extend(build_relationship_documents(relationships))
    documents.extend(build_glossary_documents(glossary))
    documents.extend(build_query_pattern_documents(query_patterns))

    return documents


def main():
    """Test metadata document generation."""

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:
        documents = build_all_documents(connection)

        print("RAG documents created successfully.")
        print("----------------------------------")
        print(f"Total documents: {len(documents)}")

        document_types = {}

        for document in documents:
            document_type = document["document_type"]
            document_types[document_type] = (
                document_types.get(document_type, 0) + 1
            )

        for document_type, count in document_types.items():
            print(f"{document_type.capitalize():<15}: {count}")

        print("\nFirst document:")
        print("----------------------------------")
        print(documents[0]["content"])

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()