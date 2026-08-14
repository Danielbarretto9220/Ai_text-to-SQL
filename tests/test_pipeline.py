"""
app/pipeline.py — end-to-end retrieval -> prompt -> LLM -> validate, plus
execute_query()'s defense-in-depth (rejected by Postgres itself via
SET TRANSACTION READ ONLY, not just app-level guardrails).

pipeline_result is module-scoped and parameterized by question so each
of the 3 canonical questions costs exactly one live Gemini call shared
across every assertion about it, per docs/API_AND_TESTING_PLAN.md B2.
"""

import pytest

from app.pipeline import execute_query, generate_validated_sql
from app.validation.sql_parser import is_read_only, parse_sql
from tests.conftest import retry_on_api_error

CANONICAL_QUESTIONS = [
    "List customers with overdue EMI payments",
    "What is the average interest rate for active loans?",
    "Which branch has the most loans?",
]


@pytest.fixture(scope="module", params=CANONICAL_QUESTIONS)
def pipeline_result(request, db_connection, embedding_model, reranker_model):
    return retry_on_api_error(
        lambda: generate_validated_sql(db_connection, request.param, embedding_model, reranker_model)
    )


@pytest.mark.live
def test_pipeline_produces_valid_sql(pipeline_result):
    assert pipeline_result["valid"] is True, pipeline_result["errors"]
    assert pipeline_result["sql"]


@pytest.mark.live
def test_pipeline_sql_is_structurally_sound(pipeline_result):
    parsed, error = parse_sql(pipeline_result["sql"])
    assert error is None
    assert is_read_only(parsed)


@pytest.mark.live
def test_execute_query_returns_rows_for_safe_select(db_connection):
    result = execute_query(db_connection, "SELECT customer_id, first_name FROM customers LIMIT 5")
    assert result["columns"]
    assert len(result["rows"]) <= 5


def test_execute_query_defense_in_depth_rejects_update(db_connection):
    """Bypasses all Python-level validation entirely by calling
    execute_query() directly with an UPDATE — Postgres itself must
    reject it (the transaction was set READ ONLY), not just app-level
    guardrails."""

    with db_connection.cursor() as cursor:
        cursor.execute("SELECT first_name FROM customers ORDER BY customer_id LIMIT 1;")
        original_value = cursor.fetchone()[0]
    db_connection.rollback()

    with pytest.raises(Exception):
        execute_query(
            db_connection,
            "UPDATE customers SET first_name = 'HACKED' "
            "WHERE customer_id = (SELECT MIN(customer_id) FROM customers);",
        )

    db_connection.rollback()

    with db_connection.cursor() as cursor:
        cursor.execute("SELECT first_name FROM customers ORDER BY customer_id LIMIT 1;")
        assert cursor.fetchone()[0] == original_value
