"""
Builds the system + user prompt from the versioned template, retrieved
context (tables, join paths, business terms), and the user's question.

The system prompt is fetched from meta.prompt_versions (already seeded —
METADATA/14-15_*.sql), not hardcoded here. The user prompt wraps the
question + assembled CONTEXT JSON + output-format instructions using
app/prompting/templates/user_prompt.txt.

See enterprise-text-to-sql-architecture.md §3.
"""

import json
import os

from app.db.metadata_loader import get_connection, load_column_metadata, load_table_metadata
from app.retrieval.confidence import retrieve_context
from app.retrieval.hybrid_search import hybrid_search
from app.retrieval.rerank import load_reranker_model
from app.retrieval.vector_search import load_embedding_model


TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def get_active_prompt(connection, prompt_name="text_to_sql_system_prompt"):
    """Fetch the active system prompt text + version number from
    meta.prompt_versions. Raises if no active row exists — a missing
    active prompt is a configuration error, not something to silently
    paper over with a fallback default."""

    query = """
        SELECT prompt_text, version_number
        FROM meta.prompt_versions
        WHERE prompt_name = %s AND is_active
        LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (prompt_name,))
        row = cursor.fetchone()

    if row is None:
        raise ValueError(f"No active prompt found for prompt_name={prompt_name!r} in meta.prompt_versions.")

    prompt_text, version_number = row
    return prompt_text, version_number


def fetch_business_terms(connection, query_text, embedding_model, top_k=3):
    """Glossary terms relevant to the question — architecture doc §3.2's
    "business_terms" context section. retrieve_context() doesn't fetch
    these (it's scoped to table/column docs for table selection), so
    this is a separate, small hybrid_search call."""

    results = hybrid_search(
        connection, query_text, embedding_model, top_k=top_k, document_types=["glossary"]
    )

    return [{"term": (r["metadata"] or {}).get("term"), "content": r["content"]} for r in results]


def fetch_query_patterns(connection, query_text, embedding_model, top_k=2):
    """Few-shot query_pattern examples relevant to the question — the
    active system prompt's rule 7 ("prefer a matching query_pattern
    example over inventing a new approach") assumes CONTEXT can contain
    these, but retrieve_context() doesn't fetch them either."""

    results = hybrid_search(
        connection, query_text, embedding_model, top_k=top_k, document_types=["query_pattern"]
    )

    return [{"content": r["content"]} for r in results]


def assemble_context(connection, retrieval_result, business_terms, query_patterns):
    """Build the CONTEXT dict (architecture doc §3.2's shape, adapted for
    this project's flat, non-medallion schema — no layer_priority)."""

    table_origin = {t["table_name"]: t["origin"] for t in retrieval_result["tables"]}
    table_names = set(table_origin)

    all_tables = load_table_metadata(connection)
    all_columns = load_column_metadata(connection)

    tables = []

    for table_id, schema_name, table_name, object_type, business_description, row_count_estimate in all_tables:
        if table_name not in table_names:
            continue

        columns = [
            {
                "name": column_name,
                "type": data_type,
                "pk": is_pk,
                "fk_ref": f"{fk_ref_table}.{fk_ref_column}" if is_fk and fk_ref_table else None,
                "synonyms": business_synonyms or [],
                "sample_values": sample_values or [],
                "description": col_business_description,
            }
            for (
                column_id,
                col_table_name,
                column_name,
                data_type,
                nullable,
                is_pk,
                is_fk,
                fk_ref_table,
                fk_ref_column,
                col_business_description,
                business_synonyms,
                sample_values,
            ) in all_columns
            if col_table_name == table_name
        ]

        tables.append(
            {
                "name": table_name,
                "type": object_type,
                "origin": table_origin[table_name],
                "business_description": business_description,
                "columns": columns,
            }
        )

    return {
        "tables": tables,
        "join_paths": retrieval_result["join_paths"],
        "business_terms": business_terms,
        "query_patterns": query_patterns,
        "confidence": retrieval_result["confidence"],
    }


def build_user_prompt(query_text, context):
    """Load templates/user_prompt.txt and interpolate the question +
    CONTEXT JSON into it."""

    template_path = os.path.join(TEMPLATES_DIR, "user_prompt.txt")

    with open(template_path, "r", encoding="utf-8") as template_file:
        template = template_file.read()

    context_json = json.dumps(context, indent=2, default=str)

    return template.format(question=query_text, context_json=context_json)


def build_prompt(connection, query_text, embedding_model=None, reranker_model=None):
    """The prompting pipeline entry point: fetch the versioned system
    prompt, run retrieval, assemble CONTEXT, and build the final user
    prompt.

    Does NOT short-circuit on retrieval_result["clarification_needed"] —
    it still builds the full prompt and surfaces the flag in the output,
    leaving the policy decision (ask the user vs. proceed anyway) to
    whichever caller owns that choice.
    """

    if embedding_model is None:
        embedding_model = load_embedding_model()

    if reranker_model is None:
        reranker_model = load_reranker_model()

    system_prompt, version_number = get_active_prompt(connection)

    retrieval_result = retrieve_context(connection, query_text, embedding_model, reranker_model)

    business_terms = fetch_business_terms(connection, query_text, embedding_model)
    query_patterns = fetch_query_patterns(connection, query_text, embedding_model)

    context = assemble_context(connection, retrieval_result, business_terms, query_patterns)

    user_prompt = build_user_prompt(query_text, context)

    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "context": context,
        "retrieval": retrieval_result,
        "prompt_version": {"prompt_name": "text_to_sql_system_prompt", "version_number": version_number},
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

        print("\nBuilding prompt...")

        result = build_prompt(connection, query_text, embedding_model, reranker_model)

        print("\n" + "=" * 70)
        print(f"SYSTEM PROMPT (v{result['prompt_version']['version_number']})")
        print("=" * 70)
        print(result["system_prompt"])

        print("\n" + "=" * 70)
        print("USER PROMPT")
        print("=" * 70)
        print(result["user_prompt"])

        confidence = result["retrieval"]["confidence"]
        print(f"\nConfidence: {confidence['label']} ({confidence['score']:.3f})")
        if result["retrieval"]["clarification_needed"]:
            print(f"Clarification needed: {result['retrieval']['clarification_reason']}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
