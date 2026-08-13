import os

import psycopg2
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer


load_dotenv()


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def get_connection():
    """Create a connection to the PostgreSQL banking database."""

    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def load_embedding_model():
    """Load the same embedding model used during indexing."""

    print("Loading embedding model...")

    model = SentenceTransformer(MODEL_NAME)

    print("Embedding model loaded.")

    return model


def generate_query_embedding(model, query_text):
    """Convert a user query into a 384-dimensional embedding."""

    embedding = model.encode(
        query_text,
        normalize_embeddings=True,
    )

    print(f"Query embedding dimensions: {len(embedding)}")

    return embedding


def search_documents(connection, query_embedding, top_k=5):
    """
    Search the pgvector database for the most similar RAG documents.

    Uses cosine distance:
        embedding <=> query_embedding

    Smaller distance means more similar.
    """

    vector_string = "[" + ",".join(map(str, query_embedding)) + "]"

    query = """
        SELECT
            document_id,
            document_type,
            content,
            metadata,
            embedding <=> %s::vector AS distance
        FROM meta.document_embeddings
        ORDER BY embedding <=> %s::vector
        LIMIT %s;
    """

    with connection.cursor() as cursor:

        cursor.execute(
            query,
            (
                vector_string,
                vector_string,
                top_k,
            ),
        )

        return cursor.fetchall()


def display_results(results):
    """Display retrieved RAG documents."""

    print("\n")
    print("=" * 70)
    print("RAG RETRIEVAL RESULTS")
    print("=" * 70)

    if not results:
        print("No documents found.")
        return

    for index, result in enumerate(results, start=1):

        document_id = result[0]
        document_type = result[1]
        content = result[2]
        metadata = result[3]
        distance = result[4]

        similarity = 1 - distance

        print(f"\nResult #{index}")
        print("-" * 70)

        print(f"Document ID : {document_id}")
        print(f"Type        : {document_type}")
        print(f"Similarity  : {similarity:.4f}")

        print("\nContent:")
        print(content)

        print("\nMetadata:")
        print(metadata)


def main():

    query_text = input(
        "\nEnter your question: "
    ).strip()

    if not query_text:
        print("No question entered.")
        return

    print("\nConnecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.")

    try:

        model = load_embedding_model()

        print("\nGenerating query embedding...")

        query_embedding = generate_query_embedding(
            model,
            query_text,
        )

        print("\nSearching pgvector...")

        results = search_documents(
            connection,
            query_embedding,
            top_k=5,
        )

        display_results(results)

    finally:

        connection.close()

        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main() 