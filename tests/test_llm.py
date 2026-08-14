"""
app/llm/client.py — live Gemini calls. Marked `live`; run the rest of the
suite with `-m "not live"` while iterating (see pytest.ini).
"""

import pytest

from app.llm.client import call_llm
from app.llm.schemas import is_error_response
from app.prompting.prompt_builder import build_prompt
from tests.conftest import retry_on_api_error


@pytest.mark.live
def test_call_llm_returns_parseable_response(db_connection, embedding_model, reranker_model):
    prompt_result = build_prompt(
        db_connection, "List customers with overdue EMI payments", embedding_model, reranker_model
    )
    result = retry_on_api_error(lambda: call_llm(prompt_result))

    assert result["response"] is not None
    response = result["response"]
    assert not is_error_response(response)
    assert response.sql
    assert response.tables_used


@pytest.mark.live
def test_call_llm_out_of_scope_question_returns_insufficient_context(db_connection, embedding_model, reranker_model):
    prompt_result = build_prompt(
        db_connection, "What is the weather in Mumbai today?", embedding_model, reranker_model
    )
    result = retry_on_api_error(lambda: call_llm(prompt_result))

    assert result["response"] is not None
    response = result["response"]
    assert is_error_response(response)
    assert response.error == "insufficient_context"
