"""
Hybrid retrieval: BM25/keyword search (Postgres tsvector, added by
METADATA/19_add_fulltext_search.sql) + dense vector search
(app/retrieval/vector_search.py), combined via Reciprocal Rank Fusion
(RRF).

See enterprise-text-to-sql-architecture.md §2.1.
"""

from app.db.session import get_connection
from app.retrieval.vector_search import (
    generate_query_embedding,
    load_embedding_model,
    search_documents,
)


def keyword_search(connection, query_text, top_k=30, document_types=None):
    """BM25-ish keyword search over meta.document_embeddings.content_tsv,
    ranked by ts_rank. Same (document_id, document_type, content, metadata,
    rank) tuple shape as vector_search.search_documents, for symmetry."""

    type_filter = "AND document_type = ANY(%s)" if document_types else ""

    query = f"""
        SELECT
            document_id,
            document_type,
            content,
            metadata,
            ts_rank(content_tsv, websearch_to_tsquery('english', %s)) AS rank
        FROM meta.document_embeddings
        WHERE content_tsv @@ websearch_to_tsquery('english', %s)
        {type_filter}
        ORDER BY rank DESC
        LIMIT %s;
    """

    params = [query_text, query_text]
    if document_types:
        params.append(document_types)
    params.append(top_k)

    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchall()


def _row_to_document(row):
    document_id, document_type, content, metadata, _score = row
    return {
        "document_id": document_id,
        "document_type": document_type,
        "content": content,
        "metadata": metadata,
    }


def reciprocal_rank_fusion(result_lists, k=60):
    """Combine multiple ranked result lists (each a list of rows shaped
    like search_documents'/keyword_search's output) into one fused
    ranking. Each document's score is the sum of 1/(k + rank) across every
    list it appears in (1-based rank within that list)."""

    scores = {}
    documents = {}

    for results in result_lists:
        for rank, row in enumerate(results, start=1):
            document_id = row[0]
            scores[document_id] = scores.get(document_id, 0.0) + 1.0 / (k + rank)
            documents.setdefault(document_id, _row_to_document(row))

    fused = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    return [
        {**documents[document_id], "rrf_score": score}
        for document_id, score in fused
    ]


def hybrid_search(connection, query_text, embedding_model, top_k=30, document_types=None):
    """Dense (vector) + sparse (keyword) legs, combined via RRF."""

    query_embedding = generate_query_embedding(embedding_model, query_text)

    vector_results = search_documents(
        connection, query_embedding, top_k=top_k, document_types=document_types
    )
    keyword_results = keyword_search(
        connection, query_text, top_k=top_k, document_types=document_types
    )

    fused = reciprocal_rank_fusion([vector_results, keyword_results])

    return fused[:top_k]


def main():

    query_text = input("\nEnter your question: ").strip()

    if not query_text:
        print("No question entered.")
        return

    print("\nConnecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.")

    try:
        model = load_embedding_model()

        print("\nRunning hybrid search (vector + keyword, RRF fused)...")

        results = hybrid_search(connection, query_text, model, top_k=10)

        print("\n" + "=" * 70)
        print("HYBRID SEARCH RESULTS")
        print("=" * 70)

        if not results:
            print("No documents found.")

        for index, document in enumerate(results, start=1):
            print(f"\nResult #{index}")
            print("-" * 70)
            print(f"Document ID : {document['document_id']}")
            print(f"Type        : {document['document_type']}")
            print(f"RRF Score   : {document['rrf_score']:.5f}")
            print("\nContent:")
            print(document["content"])

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
