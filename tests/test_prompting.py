"""
app/prompting/prompt_builder.py — no Groq calls (build_prompt() stops
short of call_llm()), so nothing here is `live`-marked.
"""

import json

import pytest

from app.prompting.prompt_builder import assemble_context, build_prompt, build_user_prompt, get_active_prompt
from app.retrieval.confidence import retrieve_context


def test_get_active_prompt_returns_active_version(db_connection):
    prompt_text, version_number = get_active_prompt(db_connection)
    assert prompt_text
    assert version_number >= 1


def test_get_active_prompt_raises_for_unknown_prompt_name(db_connection):
    with pytest.raises(ValueError):
        get_active_prompt(db_connection, prompt_name="does_not_exist")


def test_assemble_context_includes_only_selected_tables(db_connection):
    """Synthetic, deterministic retrieval_result restricted to a single
    table — real retrieve_context() output isn't used here because on
    this project's small 5-table schema, relationship expansion
    legitimately pulls in every table for some questions, which would
    make a real query an unreliable way to prove filtering happens at
    all."""

    retrieval_result = {
        "tables": [{"table_name": "customers", "origin": "matched"}],
        "join_paths": [],
        "confidence": {"score": 1.0, "label": "high"},
    }
    context = assemble_context(db_connection, retrieval_result, business_terms=[], query_patterns=[])

    context_names = {t["name"] for t in context["tables"]}
    assert context_names == {"customers"}


@pytest.mark.slow
def test_build_user_prompt_context_is_valid_json(db_connection, embedding_model, reranker_model):
    retrieval_result = retrieve_context(db_connection, "overdue EMI payments", embedding_model, reranker_model)
    context = assemble_context(db_connection, retrieval_result, business_terms=[], query_patterns=[])
    user_prompt = build_user_prompt("overdue EMI payments", context)

    context_block = user_prompt.split("CONTEXT:\n", 1)[1].split("\n\nOUTPUT FORMAT", 1)[0]
    parsed_context = json.loads(context_block)
    assert set(parsed_context.keys()) == {"tables", "join_paths", "business_terms", "query_patterns", "confidence"}


def test_build_user_prompt_output_format_has_literal_braces():
    context = {"tables": [], "join_paths": [], "business_terms": [], "query_patterns": [], "confidence": {}}
    user_prompt = build_user_prompt("test question", context)

    # templates/user_prompt.txt escapes the OUTPUT FORMAT block's braces
    # as {{ }} so .format() renders them as literal single braces.
    assert '"sql": "<postgresql query>"' in user_prompt
    assert "{{" not in user_prompt
    assert "}}" not in user_prompt


@pytest.mark.slow
def test_build_prompt_end_to_end(db_connection, embedding_model, reranker_model):
    result = build_prompt(db_connection, "overdue EMI payments", embedding_model, reranker_model)

    assert result["system_prompt"]
    assert result["user_prompt"]
    assert result["prompt_version"]["prompt_name"] == "text_to_sql_system_prompt"
    assert result["prompt_version"]["version_number"] >= 1
    assert "retrieval" in result
