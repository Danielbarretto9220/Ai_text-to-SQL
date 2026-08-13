"""
Full pipeline orchestration: retrieval -> prompt -> LLM -> validate ->
(optional) execute.

validate_sql() combines sql_parser (syntax, read-only, hallucination,
join checks) + guardrails (LIMIT injection, complexity, business rules)
+ cost_estimator (EXPLAIN) into one pass/fail report.

generate_validated_sql() is the end-to-end entry point: build_prompt()
-> call_llm() -> validate_sql() -> one repair attempt on validation
failure (re-calls the LLM with the validation errors appended — a
separate retry loop from app/llm/client.py's own repair retry, which
only covers malformed *JSON shape*, not SQL *content* failing
validation), matching architecture doc §5's "one automatic repair
attempt" wording.

execute_query() is NOT auto-invoked by generate_validated_sql() — it's
opt-in only, with real safety rails (SET TRANSACTION READ ONLY,
statement_timeout, row cap, always rolled back afterward, never
commits). This is the first code path in this project capable of
running arbitrary LLM-generated SQL against the real database, so it's
deliberately never automatic.

See enterprise-text-to-sql-architecture.md §4, §5.
"""

from app.db.session import get_connection
from app.llm.client import call_llm
from app.llm.schemas import is_error_response
from app.prompting.prompt_builder import build_prompt
from app.retrieval.rerank import load_reranker_model
from app.retrieval.vector_search import load_embedding_model
from app.validation.cost_estimator import check_cost
from app.validation.guardrails import run_guardrails
from app.validation.sql_parser import check_hallucinations, check_joins, is_read_only, parse_sql


def validate_sql(connection, sql_text, question_text):
    """Runs sql_parser -> guardrails -> cost_estimator, combined into one
    report: {valid, final_sql, errors, warnings, limit_injected, cost}."""

    parsed, syntax_error = parse_sql(sql_text)
    if syntax_error:
        return {
            "valid": False,
            "final_sql": sql_text,
            "errors": [f"Syntax error: {syntax_error}"],
            "warnings": [],
            "limit_injected": False,
            "cost": None,
        }

    if not is_read_only(parsed):
        return {
            "valid": False,
            "final_sql": sql_text,
            "errors": ["Query is not read-only (must be a SELECT statement)."],
            "warnings": [],
            "limit_injected": False,
            "cost": None,
        }

    reference_errors = check_hallucinations(connection, parsed) + check_joins(connection, parsed)

    guardrail_result = run_guardrails(connection, parsed, sql_text, question_text)

    errors = list(reference_errors) + list(guardrail_result["errors"])
    warnings = list(guardrail_result["warnings"])
    cost = None

    # EXPLAIN would itself error against a hallucinated table/column, so only
    # cost-check SQL already confirmed to reference real schema objects.
    if not reference_errors:
        cost_result = check_cost(connection, guardrail_result["final_sql"])
        cost = {"total_cost": cost_result["total_cost"], "plan_rows": cost_result["plan_rows"]}
        errors.extend(cost_result["errors"])

    return {
        "valid": len(errors) == 0,
        "final_sql": guardrail_result["final_sql"],
        "errors": errors,
        "warnings": warnings,
        "limit_injected": guardrail_result["limit_injected"],
        "cost": cost,
    }


def _result(question_text, retrieval_result, retried, sql=None, valid=False, errors=None, warnings=None,
            tables_used=None, confidence=None, cost=None):
    return {
        "question": question_text,
        "sql": sql,
        "valid": valid,
        "errors": errors or [],
        "warnings": warnings or [],
        "tables_used": tables_used or [],
        "confidence": confidence,
        "retrieval": retrieval_result,
        "cost": cost,
        "retried_for_validation": retried,
    }


def generate_validated_sql(connection, question_text, embedding_model=None, reranker_model=None):
    """The end-to-end pipeline entry point."""

    if embedding_model is None:
        embedding_model = load_embedding_model()

    if reranker_model is None:
        reranker_model = load_reranker_model()

    prompt_result = build_prompt(connection, question_text, embedding_model, reranker_model)
    retrieval_result = prompt_result["retrieval"]

    llm_result = call_llm(prompt_result)
    response = llm_result["response"]

    if response is None:
        return _result(
            question_text, retrieval_result, False,
            errors=[f"LLM failed to produce a parseable response: {llm_result['raw_text']}"],
        )

    if is_error_response(response):
        return _result(
            question_text, retrieval_result, False,
            errors=[f"Insufficient context: {response.missing}"], confidence=response.confidence,
        )

    validation = validate_sql(connection, response.sql, question_text)
    retried = False

    if not validation["valid"]:
        retried = True

        repair_prompt_result = {
            **prompt_result,
            "user_prompt": (
                prompt_result["user_prompt"]
                + f"\n\nYour SQL failed validation: {validation['errors']}. "
                "Return corrected JSON matching the schema."
            ),
        }

        llm_result = call_llm(repair_prompt_result)
        response = llm_result["response"]

        if response is None:
            return _result(
                question_text, retrieval_result, True,
                errors=[f"Repair attempt failed to produce a parseable response: {llm_result['raw_text']}"],
            )

        if is_error_response(response):
            return _result(
                question_text, retrieval_result, True,
                errors=[f"Insufficient context (after repair attempt): {response.missing}"],
                confidence=response.confidence,
            )

        validation = validate_sql(connection, response.sql, question_text)

    return _result(
        question_text, retrieval_result, retried,
        sql=response.sql, valid=validation["valid"], errors=validation["errors"],
        warnings=validation["warnings"], tables_used=response.tables_used,
        confidence=response.confidence, cost=validation.get("cost"),
    )


def execute_query(connection, sql_text, row_cap=1000, statement_timeout_ms=5000):
    """Opt-in only — never called automatically by generate_validated_sql().
    SET TRANSACTION READ ONLY + statement_timeout inside the transaction,
    fetches up to row_cap rows, always rolls back afterward (never
    commits — correct for a read-only transaction, and an extra safety
    margin even for a plain SELECT)."""

    connection.rollback()  # clean transaction boundary before SET TRANSACTION

    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION READ ONLY;")
        cursor.execute(f"SET statement_timeout = {int(statement_timeout_ms)};")
        cursor.execute(sql_text)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchmany(row_cap)

    connection.rollback()

    return {"columns": columns, "rows": rows}


def main():

    print("Connecting to PostgreSQL...")

    connection = get_connection()

    print("Connected successfully.")

    try:
        question_text = input("\nEnter your question: ").strip()

        if not question_text:
            print("No question entered.")
            return

        embedding_model = load_embedding_model()
        reranker_model = load_reranker_model()

        print("\nRunning full pipeline (retrieval -> prompt -> LLM -> validate)...")

        result = generate_validated_sql(connection, question_text, embedding_model, reranker_model)

        print("\n" + "=" * 70)
        print("RESULT")
        print("=" * 70)
        print(f"Valid: {result['valid']}")
        print(f"Retried for validation: {result['retried_for_validation']}")
        print(f"SQL: {result['sql']}")
        print(f"Tables used: {result['tables_used']}")
        print(f"Confidence: {result['confidence']}")
        print(f"Cost: {result['cost']}")
        print(f"Errors: {result['errors']}")
        print(f"Warnings: {result['warnings']}")

        if result["valid"] and result["sql"]:
            choice = input("\nExecute this query? (y/n): ").strip().lower()
            if choice == "y":
                execution = execute_query(connection, result["sql"])
                print(f"\nColumns: {execution['columns']}")
                print(f"Rows ({len(execution['rows'])}):")
                for row in execution["rows"]:
                    print(f"  {row}")

    finally:
        connection.close()
        print("\nPostgreSQL connection closed.")


if __name__ == "__main__":
    main()
