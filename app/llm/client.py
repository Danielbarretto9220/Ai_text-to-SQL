"""
LLM client (Google AI Studio / Gemini, via the google-genai SDK).

Takes app/prompting/prompt_builder.py's build_prompt() output directly
(system_prompt, user_prompt) and returns a validated
SQLGenerationResponse. Does NOT do SQL validation, guardrails, cost
estimation, or pipeline orchestration — those are separate, later
phases (app/validation/*, and an unbuilt orchestration layer).

See enterprise-text-to-sql-architecture.md §6.5, §8, §3.4.
"""

import json

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.llm.schemas import SQLGenerationResponse


def get_client():
    """Create a genai.Client using the configured API key. Raises clearly
    if GEMINI_API_KEY is unset — fails at point of use, not at import
    time, so importing this module never breaks callers that don't
    need it."""

    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set — add it to .env.")

    return genai.Client(api_key=GEMINI_API_KEY)


def generate_sql(client, system_prompt, user_prompt, model=None):
    """One Gemini call: temperature 0 (architecture doc §3.4 —
    determinism), strict JSON output constrained to SQLGenerationResponse
    via response_schema. Returns the raw response text."""

    response = client.models.generate_content(
        model=model or GEMINI_MODEL,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,
            response_mime_type="application/json",
            response_schema=SQLGenerationResponse,
        ),
    )

    return response.text


def parse_response(raw_text):
    """Validate raw_text against SQLGenerationResponse. Returns
    (response, None) on success or (None, error_message) on failure,
    so the caller can decide whether to retry rather than this
    function raising."""

    try:
        return SQLGenerationResponse.model_validate_json(raw_text), None
    except (ValidationError, json.JSONDecodeError) as exc:
        return None, str(exc)


def call_llm(prompt_result, client=None, model=None):
    """The entry point: takes prompt_builder.build_prompt()'s output dict
    directly. One automatic repair retry on parse/validation failure
    (architecture doc §3.4), appending the error to the user prompt and
    asking for corrected JSON.

    Returns {"response": SQLGenerationResponse | None, "raw_text": str,
    "retried": bool}. Does not interpret is_error_response() itself —
    that's left to the caller.
    """

    if client is None:
        client = get_client()

    system_prompt = prompt_result["system_prompt"]
    user_prompt = prompt_result["user_prompt"]

    raw_text = generate_sql(client, system_prompt, user_prompt, model=model)
    response, error = parse_response(raw_text)

    if response is not None:
        return {"response": response, "raw_text": raw_text, "retried": False}

    repair_prompt = (
        f"{user_prompt}\n\n"
        f"Your previous response failed validation: {error}. "
        "Return corrected JSON matching the schema."
    )

    raw_text = generate_sql(client, system_prompt, repair_prompt, model=model)
    response, error = parse_response(raw_text)

    return {"response": response, "raw_text": raw_text, "retried": True}


def main():

    from app.db.session import get_connection
    from app.prompting.prompt_builder import build_prompt
    from app.retrieval.rerank import load_reranker_model
    from app.retrieval.vector_search import load_embedding_model

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

        print("\nBuilding prompt...")
        prompt_result = build_prompt(connection, query_text, embedding_model, reranker_model)

        print(f"System prompt version: {prompt_result['prompt_version']}")

        print("\nCalling Gemini...")
        result = call_llm(prompt_result)

        print("\n" + "=" * 70)
        print("RAW RESPONSE")
        print("=" * 70)
        print(result["raw_text"])
        print(f"\nRetried: {result['retried']}")

        response = result["response"]

        print("\n" + "=" * 70)
        print("PARSED RESPONSE")
        print("=" * 70)

        if response is None:
            print("Failed to parse a valid response after retry.")
        else:
            print(response.model_dump_json(indent=2))

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
