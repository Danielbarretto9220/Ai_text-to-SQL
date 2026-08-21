"""
LLM client (Groq, via the `openai` SDK — Groq documents its API as an
OpenAI-compatible drop-in).

Takes app/prompting/prompt_builder.py's build_prompt() output dict directly
(system_prompt, user_prompt) and returns a validated SQLGenerationResponse.
Does NOT do SQL validation, guardrails, cost estimation, or pipeline
orchestration — those are separate, later phases (app/validation/*, and
app/pipeline.py).

This module has targeted Gemini, xAI Grok, and Anthropic Claude in turn;
it was rewritten for Groq on 2026-08-21 — the prior providers all require
paid billing before any call succeeds, and Groq is the one with a genuinely
free (no-card) tier, at the cost of tighter rate limits.

Model selection is tiered rather than fixed: GROQ_MODEL (openai/gpt-oss-20b
by default, app/config.py) handles every first attempt — smaller and
faster, and sufficient for the large majority of well-scoped text-to-SQL
questions. call_llm()'s one automatic repair retry (architecture doc §3.4)
escalates to GROQ_ESCALATION_MODEL (openai/gpt-oss-120b by default) instead
of re-asking the smaller model with the same error appended — a
shape/validation failure on the first model is exactly the "needs a more
capable model, not another attempt at the same one" case.

**response_format is JSON Object mode, not JSON Schema strict mode —
deliberately, not as an oversight.** Groq documents `response_format:
{"type": "json_schema", "json_schema": {"strict": true, ...}}` as supported
on both openai/gpt-oss-20b and openai/gpt-oss-120b, and it was tried first
here. It does not work for this project's schema: SQLGenerationResponse's
optional fields serialize (via Pydantic's model_json_schema()) as
`anyOf: [{type: ...}, {type: "null"}]`, and Groq's strict-mode validator
rejects a model-generated `null` for those fields with `does not validate
with /properties/<field>/type: expected string, but got null` — even
though the generation was correct per the schema. Confirmed live against
both models with the actual schema before writing this module; this is a
Groq-side validator limitation with anyOf/nullable fields, not a prompt or
schema-authoring mistake. JSON Object mode (used here) only constrains the
output to *be* a JSON object, not to match SQLGenerationResponse's exact
shape — weaker than the schema guarantee this project used with Anthropic
Claude — so the OUTPUT FORMAT block in app/prompting/templates/user_prompt.txt
carries the actual shape instruction, and parse_response() + call_llm()'s
repair retry are what actually catch a mismatch. Revisit json_schema strict
mode if Groq fixes the anyOf/null validation — it would be a real
improvement, not just a preference.
"""

import json

from openai import OpenAI
from pydantic import ValidationError

from app.config import GROQ_API_KEY, GROQ_ESCALATION_MODEL, GROQ_MODEL
from app.llm.schemas import SQLGenerationResponse

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


def get_client():
    """Create an OpenAI-SDK client pointed at Groq's endpoint. Raises
    clearly if GROQ_API_KEY is unset — fails at point of use, not at
    import time, so importing this module never breaks callers that
    don't need it."""

    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set — add it to .env.")

    return OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)


def generate_sql(client, system_prompt, user_prompt, model=None):
    """One Groq call: JSON Object mode (response_format={"type":
    "json_object"}) — see this module's docstring for why JSON Schema
    strict mode isn't used despite being documented as supported. Returns
    the raw response text."""

    response = client.chat.completions.create(
        model=model or GROQ_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.choices[0].message.content


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
    escalating from GROQ_MODEL to GROQ_ESCALATION_MODEL — unless the caller
    passed an explicit `model`, in which case both attempts use it (no
    escalation), matching the single-model behavior the test suite relies
    on.

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

    raw_text = generate_sql(client, system_prompt, repair_prompt, model=model or GROQ_ESCALATION_MODEL)
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

        print("\nCalling Groq...")
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
