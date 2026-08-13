"""
Embedding indexing worker: builds RAG documents from meta.* and upserts
their embeddings into meta.document_embeddings (pgvector).

Currently a full rebuild on every run. Incremental re-indexing via
content_hash diffing (architecture doc §1.6) is not yet implemented.
"""

from psycopg2.extras import Json
from sentence_transformers import SentenceTransformer

from app.db.session import get_connection
from app.retrieval.document_builder import build_all_documents


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def generate_document_id(document):
    """Generate a stable unique ID for each RAG document."""

    document_type = document["document_type"]
    metadata = document["metadata"]

    if document_type == "table":
        return f"table:{metadata['schema_name']}:{metadata['table_name']}"

    elif document_type == "column":
        return (
            f"column:{metadata['table_name']}:"
            f"{metadata['column_name']}"
        )

    elif document_type == "relationship":
        return f"relationship:{metadata['relationship_id']}"

    elif document_type == "glossary":
        return f"glossary:{metadata['term_id']}"

    raise ValueError(
        f"Unknown document type: {document_type}"
    )


def generate_embeddings(documents):
    """Generate 384-dimensional embeddings for documents."""

    print("Loading embedding model...")

    model = SentenceTransformer(MODEL_NAME)

    contents = [
        document["content"]
        for document in documents
    ]

    print(
        f"Generating embeddings for {len(contents)} documents..."
    )

    embeddings = model.encode(
        contents,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    return embeddings


def save_embeddings(connection, documents, embeddings):
    """Save embeddings into meta.document_embeddings."""

    query = """
        INSERT INTO meta.document_embeddings
            (
                document_id,
                document_type,
                content,
                embedding,
                metadata
            )
        VALUES
            (%s, %s, %s, %s, %s)
        ON CONFLICT (document_id)
        DO UPDATE SET
            document_type = EXCLUDED.document_type,
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            metadata = EXCLUDED.metadata;
    """

    with connection.cursor() as cursor:

        for document, embedding in zip(documents, embeddings):

            document_id = generate_document_id(document)
            document_type = document["document_type"]
            content = document["content"]
            metadata = document["metadata"]

            vector_string = (
                "[" + ",".join(map(str, embedding)) + "]"
            )

            cursor.execute(
                query,
                (
                    document_id,
                    document_type,
                    content,
                    vector_string,
                    Json(metadata),
                ),
            )

    connection.commit()


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.\n")

    try:

        print("Building RAG documents...")

        documents = build_all_documents(connection)

        print(
            f"RAG documents loaded: {len(documents)}"
        )

        if not documents:
            print("No RAG documents found.")
            return

        print()

        embeddings = generate_embeddings(documents)

        print(
            f"\nEmbedding dimensions: {embeddings.shape[1]}"
        )

        save_embeddings(
            connection,
            documents,
            embeddings,
        )

        print(
            "\nEmbeddings saved successfully."
        )

    finally:

        connection.close()

        print(
            "PostgreSQL connection closed."
        )


if __name__ == "__main__":
    main() 