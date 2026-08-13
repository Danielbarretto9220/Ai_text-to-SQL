"""
Embedding indexing worker: builds RAG documents from meta.* and upserts
their embeddings into meta.document_embeddings (pgvector).

Two modes:
    main() / python -m workers.reindex_embeddings — full rebuild, embeds
        every document every run. Still stamps content_hash on each row
        (via save_embeddings), so a subsequent incremental_reindex() has
        something to diff against.
    incremental_reindex() — used by workers/drift_detector.py. Only
        embeds documents whose content_hash changed (or are new), and
        deletes rows for documents that no longer exist (e.g. a dropped
        column). Implements architecture doc §1.6's "only chunks whose
        hash changed are re-embedded".
"""

from psycopg2.extras import Json
from sentence_transformers import SentenceTransformer

from app.db.session import get_connection
from app.retrieval.document_builder import build_all_documents, compute_content_hash


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

    elif document_type == "query_pattern":
        return f"query_pattern:{metadata['pattern_id']}"

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
    """Save embeddings into meta.document_embeddings, stamping content_hash."""

    query = """
        INSERT INTO meta.document_embeddings
            (
                document_id,
                document_type,
                content,
                embedding,
                metadata,
                content_hash
            )
        VALUES
            (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (document_id)
        DO UPDATE SET
            document_type = EXCLUDED.document_type,
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            metadata = EXCLUDED.metadata,
            content_hash = EXCLUDED.content_hash;
    """

    with connection.cursor() as cursor:

        for document, embedding in zip(documents, embeddings):

            document_id = generate_document_id(document)
            document_type = document["document_type"]
            content = document["content"]
            metadata = document["metadata"]
            content_hash = compute_content_hash(document)

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
                    content_hash,
                ),
            )

    connection.commit()


def delete_stale_documents(connection, valid_document_ids):
    """Delete meta.document_embeddings rows whose document_id no longer
    appears in the current document set (e.g. a dropped column/table).

    Returns the list of deleted document_ids.
    """

    with connection.cursor() as cursor:
        cursor.execute("SELECT document_id FROM meta.document_embeddings;")
        existing_ids = {row[0] for row in cursor.fetchall()}

    stale_ids = list(existing_ids - set(valid_document_ids))

    if stale_ids:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM meta.document_embeddings WHERE document_id = ANY(%s);",
                (stale_ids,),
            )
        connection.commit()

    return stale_ids


def incremental_reindex(connection):
    """Only (re-)embed documents whose content actually changed, and delete
    embeddings for documents that no longer exist. Used by
    workers/drift_detector.py; implements architecture doc §1.6's
    content_hash-based incremental re-indexing.

    Returns {"embedded": [...], "unchanged": n, "deleted": [...]}.
    """

    documents = build_all_documents(connection)

    with connection.cursor() as cursor:
        cursor.execute("SELECT document_id, content_hash FROM meta.document_embeddings;")
        existing_hashes = dict(cursor.fetchall())

    changed_documents = []
    unchanged_count = 0

    for document in documents:
        document_id = generate_document_id(document)
        new_hash = compute_content_hash(document)

        if existing_hashes.get(document_id) != new_hash:
            changed_documents.append(document)
        else:
            unchanged_count += 1

    if changed_documents:
        embeddings = generate_embeddings(changed_documents)
        save_embeddings(connection, changed_documents, embeddings)

    valid_document_ids = [generate_document_id(document) for document in documents]
    deleted_ids = delete_stale_documents(connection, valid_document_ids)

    return {
        "embedded": [generate_document_id(document) for document in changed_documents],
        "unchanged": unchanged_count,
        "deleted": deleted_ids,
    }


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