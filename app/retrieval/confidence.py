"""
Confidence scoring + ambiguity-clarification path, and retrieve_context():
the retrieval pipeline entry point that ties hybrid_search.py, rerank.py,
and relationship_graph.py together.

Confidence blends the top re-ranker score with the FK-graph connectivity
of the selected tables (architecture doc §2.2): a high-scoring match
against a set of tables that don't actually join to each other is less
trustworthy than one that forms a connected subgraph.

See enterprise-text-to-sql-architecture.md §2.2, §5.
"""

import math

from app.db.session import get_connection
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.rerank import load_reranker_model, rerank
from app.retrieval.relationship_graph import get_join_path, get_related_tables
from app.retrieval.vector_search import load_embedding_model


HIGH_CONFIDENCE_THRESHOLD = 0.7
MEDIUM_CONFIDENCE_THRESHOLD = 0.4
AMBIGUITY_MARGIN = 0.05


def _sigmoid(x):
    """Squash an unbounded cross-encoder logit into (0, 1)."""

    return 1.0 / (1.0 + math.exp(-x))


def compute_confidence(reranked_results, connectivity_ratio):
    """Blend the top re-ranker score (sigmoid-squashed) with connectivity
    ratio (fraction of selected tables that join to at least one other
    selected table). Returns (score: float 0-1, label: high|medium|low)."""

    if not reranked_results:
        return 0.0, "low"

    top_score = _sigmoid(reranked_results[0]["rerank_score"])

    score = 0.7 * top_score + 0.3 * connectivity_ratio

    if score >= HIGH_CONFIDENCE_THRESHOLD:
        label = "high"
    elif score >= MEDIUM_CONFIDENCE_THRESHOLD:
        label = "medium"
    else:
        label = "low"

    return score, label


def needs_clarification(reranked_results, confidence_score):
    """Flags low confidence, or two top candidates from different tables
    with near-identical re-rank scores (ambiguous between two
    similar-meaning tables — architecture doc §3.1 rule 7).

    Returns (needs_clarification: bool, reason: str | None).
    """

    if confidence_score < MEDIUM_CONFIDENCE_THRESHOLD:
        return True, "low_confidence"

    if len(reranked_results) < 2:
        return False, None

    top, second = reranked_results[0], reranked_results[1]
    top_table = (top.get("metadata") or {}).get("table_name")
    second_table = (second.get("metadata") or {}).get("table_name")

    if top_table and second_table and top_table != second_table:
        margin = abs(_sigmoid(top["rerank_score"]) - _sigmoid(second["rerank_score"]))
        if margin < AMBIGUITY_MARGIN:
            return True, "ambiguous_tables"

    return False, None


def retrieve_context(
    connection,
    query_text,
    embedding_model=None,
    reranker_model=None,
    top_k_candidates=30,
    top_k_final=8,
):
    """The retrieval pipeline entry point: hybrid search -> re-rank ->
    relationship expansion -> confidence scoring.

    Scoped to document_type in ("table", "column") for table selection —
    those are the only document types whose metadata carries table_name
    (glossary/query-pattern documents don't), so they're what drive which
    tables get selected and expanded.
    """

    if embedding_model is None:
        embedding_model = load_embedding_model()

    if reranker_model is None:
        reranker_model = load_reranker_model()

    candidates = hybrid_search(
        connection,
        query_text,
        embedding_model,
        top_k=top_k_candidates,
        document_types=["table", "column"],
    )

    reranked = rerank(reranker_model, query_text, candidates, top_k=top_k_final)

    matched_tables = {
        (doc.get("metadata") or {}).get("table_name")
        for doc in reranked
    }
    matched_tables.discard(None)

    selected_tables = {table_name: "matched" for table_name in matched_tables}

    for table_name in matched_tables:
        for related_table in get_related_tables(connection, table_name):
            selected_tables.setdefault(related_table, "expansion")

    table_names = sorted(selected_tables)

    join_paths = []
    seen_pairs = set()

    for i, table_a in enumerate(table_names):
        for table_b in table_names[i + 1 :]:
            pair_key = (table_a, table_b)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            path = get_join_path(connection, table_a, table_b)
            if path:
                join_paths.append({"from": table_a, "to": table_b, "path": path})

    if len(table_names) <= 1:
        connectivity_ratio = 1.0
    else:
        connected_tables = {
            table_name for join_path in join_paths for table_name in (join_path["from"], join_path["to"])
        }
        connectivity_ratio = len(connected_tables) / len(table_names)

    confidence_score, confidence_label = compute_confidence(reranked, connectivity_ratio)
    clarification_needed, clarification_reason = needs_clarification(reranked, confidence_score)

    return {
        "question": query_text,
        "tables": [
            {"table_name": table_name, "origin": selected_tables[table_name]}
            for table_name in table_names
        ],
        "join_paths": join_paths,
        "confidence": {"score": confidence_score, "label": confidence_label},
        "clarification_needed": clarification_needed,
        "clarification_reason": clarification_reason,
        "candidates": reranked,
    }


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

        print("\nRetrieving context...")

        result = retrieve_context(connection, query_text, embedding_model, reranker_model)

        print("\n" + "=" * 70)
        print("RETRIEVED CONTEXT")
        print("=" * 70)

        print(f"\nQuestion: {result['question']}")

        print("\nSelected tables:")
        for table in result["tables"]:
            print(f"  - {table['table_name']} ({table['origin']})")

        print("\nJoin paths:")
        if not result["join_paths"]:
            print("  (none)")
        for join_path in result["join_paths"]:
            hops = " -> ".join(
                f"{hop['from_table']}.{hop['from_column']}={hop['to_table']}.{hop['to_column']}"
                for hop in join_path["path"]
            )
            print(f"  {join_path['from']} -> {join_path['to']}: {hops}")

        confidence = result["confidence"]
        print(f"\nConfidence: {confidence['label']} ({confidence['score']:.3f})")

        if result["clarification_needed"]:
            print(f"Clarification needed: {result['clarification_reason']}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
