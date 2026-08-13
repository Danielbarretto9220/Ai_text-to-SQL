"""
Cross-encoder re-ranking of hybrid_search.py candidates
(cross-encoder/ms-marco-MiniLM-L-6-v2 — lightweight and local, consistent
with this project's all-MiniLM-L6-v2 embedding choice), narrowing top ~30
down to top 5-8.

See enterprise-text-to-sql-architecture.md §2.1.
"""

from sentence_transformers import CrossEncoder

from app.db.session import get_connection
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.vector_search import load_embedding_model


MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def load_reranker_model():
    """Load the cross-encoder re-ranker model."""

    print("Loading reranker model...")

    model = CrossEncoder(MODEL_NAME)

    print("Reranker model loaded.")

    return model


def rerank(model, query_text, candidates, top_k=8):
    """Re-score candidates (dicts with a "content" key, as produced by
    hybrid_search.hybrid_search) with a cross-encoder, attach
    "rerank_score", and return the top_k in descending score order."""

    if not candidates:
        return []

    pairs = [(query_text, candidate["content"]) for candidate in candidates]

    scores = model.predict(pairs)

    for candidate, score in zip(candidates, scores):
        candidate["rerank_score"] = float(score)

    candidates.sort(key=lambda candidate: candidate["rerank_score"], reverse=True)

    return candidates[:top_k]


def main():

    query_text = input("\nEnter your question: ").strip()

    if not query_text:
        print("No question entered.")
        return

    print("\nConnecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.")

    try:
        embedding_model = load_embedding_model()
        reranker_model = load_reranker_model()

        print("\nRunning hybrid search...")
        candidates = hybrid_search(connection, query_text, embedding_model, top_k=30)

        print("Reranking candidates...")
        results = rerank(reranker_model, query_text, candidates, top_k=8)

        print("\n" + "=" * 70)
        print("RERANKED RESULTS")
        print("=" * 70)

        for index, document in enumerate(results, start=1):
            print(f"\nResult #{index}")
            print("-" * 70)
            print(f"Document ID  : {document['document_id']}")
            print(f"Type         : {document['document_type']}")
            print(f"RRF Score    : {document['rrf_score']:.5f}")
            print(f"Rerank Score : {document['rerank_score']:.5f}")
            print("\nContent:")
            print(document["content"])

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
