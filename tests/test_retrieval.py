"""
app/retrieval/* — vector search, keyword search, RRF fusion, reranking,
join-path BFS, and the retrieve_context() pipeline entry point.

No Gemini calls here (only the local embedding + cross-encoder models),
so nothing in this file is `live`-marked — but model inference is slower
than pure-Python validation, hence a couple of `slow` marks.
"""

import pytest

from app.retrieval.confidence import retrieve_context
from app.retrieval.hybrid_search import hybrid_search, keyword_search, reciprocal_rank_fusion
from app.retrieval.relationship_graph import get_join_path
from app.retrieval.rerank import rerank
from app.retrieval.vector_search import generate_query_embedding, search_documents


def test_vector_search_returns_results(db_connection, embedding_model):
    query_embedding = generate_query_embedding(embedding_model, "overdue EMI payments")
    results = search_documents(db_connection, query_embedding, top_k=5)
    assert results
    assert len(results) <= 5


def test_keyword_search_returns_results(db_connection):
    results = keyword_search(db_connection, "overdue payments", top_k=5)
    assert results


def test_reciprocal_rank_fusion_surfaces_documents_unique_to_either_leg():
    """Deterministic, synthetic-data test of the RRF math itself: a
    document that only the keyword leg found (never returned by the
    vector leg) must still surface in the fused ranking."""

    vector_results = [
        ("doc:vector_only", "table", "content v", None, 0.1),
        ("doc:both", "table", "content b", None, 0.2),
    ]
    keyword_results = [
        ("doc:keyword_only", "table", "content k", None, 0.9),
        ("doc:both", "table", "content b", None, 0.5),
    ]

    fused = reciprocal_rank_fusion([vector_results, keyword_results])
    fused_ids = {d["document_id"] for d in fused}

    assert "doc:vector_only" in fused_ids
    assert "doc:keyword_only" in fused_ids
    assert "doc:both" in fused_ids


def test_hybrid_search_returns_fused_results(db_connection, embedding_model):
    results = hybrid_search(db_connection, "overdue EMI payments", embedding_model, top_k=10)
    assert results
    assert all("rrf_score" in r for r in results)


@pytest.mark.slow
def test_reranking_changes_ordering(embedding_model, reranker_model):
    """RRF-fed order is deliberately wrong here (the irrelevant document
    ranked first) so that a cross-encoder pass that actually reads
    content must reorder them to prove it's doing real work, not just
    passing the input through."""

    candidates = [
        {
            "document_id": "d_irrelevant",
            "document_type": "table",
            "metadata": {},
            "content": "TABLE branches physical bank branch locations and addresses.",
            "rrf_score": 0.9,
        },
        {
            "document_id": "d_relevant",
            "document_type": "column",
            "metadata": {},
            "content": (
                "COLUMN Table: loans Column: interest_rate Business Description: "
                "Annual interest rate percentage charged on the loan."
            ),
            "rrf_score": 0.1,
        },
    ]

    results = rerank(reranker_model, "what is the interest rate on this loan", candidates, top_k=2)

    assert [r["document_id"] for r in results] == ["d_relevant", "d_irrelevant"]
    assert results[0]["rerank_score"] > results[1]["rerank_score"]


def test_get_join_path_two_hop(db_connection):
    path = get_join_path(db_connection, "emi_payments", "customers")
    assert path is not None
    assert len(path) == 2
    assert path[0]["from_table"] == "emi_payments"
    assert path[0]["to_table"] == "loans"
    assert path[-1]["to_table"] == "customers"


def test_get_join_path_same_table_is_empty(db_connection):
    assert get_join_path(db_connection, "loans", "loans") == []


def test_get_join_path_unknown_table_is_none(db_connection):
    assert get_join_path(db_connection, "loans", "nonexistent_table") is None


@pytest.mark.slow
def test_retrieve_context_returns_documented_keys(db_connection, embedding_model, reranker_model):
    result = retrieve_context(db_connection, "overdue EMI payments", embedding_model, reranker_model)

    assert set(result.keys()) == {
        "question",
        "tables",
        "join_paths",
        "confidence",
        "clarification_needed",
        "clarification_reason",
        "candidates",
    }
    assert result["tables"]
    assert result["confidence"]["label"] in {"high", "medium", "low"}
