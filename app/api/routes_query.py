"""
POST /api/v1/query — { question } -> { sql, tables_used, assumptions,
confidence, results? }
POST /api/v1/execute — explicit execution of previously-validated SQL,
separate from generation, for auditability.

See enterprise-text-to-sql-architecture.md §6.4, §4.
"""

import time

from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg2.extras import Json

from app.api.deps import get_db
from app.api.metrics import (
    executions_total,
    llm_repair_retries_total,
    queries_generated_total,
    query_latency_seconds,
    validation_failures_total,
)
from app.api.schemas import (
    ConfidenceInfo,
    CostInfo,
    ExecuteRequest,
    ExecuteResponse,
    QueryRequest,
    QueryResponse,
)
from app.config import EXECUTE_ENABLED, EXECUTE_ROW_CAP, EXECUTE_STATEMENT_TIMEOUT_MS
from app.pipeline import execute_query, generate_validated_sql, validate_sql

router = APIRouter()


def _log_query(connection, question, result, latency_ms):
    retrieval_confidence = result["retrieval"]["confidence"]

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO meta.query_log
                (question, generated_sql, is_valid, errors, warnings, tables_used,
                 llm_confidence, retrieval_confidence, retrieval_label, estimated_cost,
                 estimated_rows, retried_for_validation, prompt_version, latency_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING query_id;
            """,
            (
                question,
                result["sql"],
                result["valid"],
                Json(result["errors"]),
                Json(result["warnings"]),
                result["tables_used"],
                result["confidence"],
                retrieval_confidence["score"],
                retrieval_confidence["label"],
                result["cost"]["total_cost"] if result["cost"] else None,
                result["cost"]["plan_rows"] if result["cost"] else None,
                result["retried_for_validation"],
                result["prompt_version"],
                latency_ms,
            ),
        )
        query_id = cursor.fetchone()[0]

    connection.commit()

    return query_id


@router.post("/query", response_model=QueryResponse)
def post_query(payload: QueryRequest, request: Request, connection=Depends(get_db)):
    queries_generated_total.inc()

    start = time.monotonic()
    result = generate_validated_sql(
        connection, payload.question, request.app.state.embedding_model, request.app.state.reranker_model
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    query_latency_seconds.observe(latency_ms / 1000)

    if not result["valid"]:
        validation_failures_total.inc()
    if result["retried_for_validation"]:
        llm_repair_retries_total.inc()

    query_id = _log_query(connection, payload.question, result, latency_ms)

    columns = None
    rows = None

    if payload.execute and EXECUTE_ENABLED and result["valid"] and result["sql"]:
        execution = execute_query(
            connection, result["sql"], row_cap=EXECUTE_ROW_CAP,
            statement_timeout_ms=EXECUTE_STATEMENT_TIMEOUT_MS,
        )
        executions_total.inc()
        columns = execution["columns"]
        rows = [list(row) for row in execution["rows"]]

    cost = CostInfo(**result["cost"]) if result["cost"] else None

    return QueryResponse(
        query_id=query_id,
        question=payload.question,
        sql=result["sql"],
        valid=result["valid"],
        errors=result["errors"],
        warnings=result["warnings"],
        tables_used=result["tables_used"],
        llm_confidence=result["confidence"],
        retrieval_confidence=ConfidenceInfo(**result["retrieval"]["confidence"]),
        cost=cost,
        retried_for_validation=result["retried_for_validation"],
        columns=columns,
        results=rows,
        selected_tables=result["retrieval"]["tables"],
        join_paths=result["retrieval"]["join_paths"],
    )


@router.post("/execute", response_model=ExecuteResponse)
def post_execute(payload: ExecuteRequest, connection=Depends(get_db)):
    if not EXECUTE_ENABLED:
        raise HTTPException(status_code=403, detail="Execution is disabled (EXECUTE_ENABLED=false).")

    sql_text = payload.sql
    question_text = payload.question or ""

    if payload.query_id is not None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT generated_sql, question FROM meta.query_log WHERE query_id = %s;",
                (payload.query_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"No query_log row for query_id={payload.query_id}.")
        sql_text, question_text = row[0], row[1]

    if not sql_text:
        raise HTTPException(status_code=400, detail="No SQL provided (via query_id or sql).")

    # Never trust a client-supplied SQL string just because an earlier
    # response contained it — re-validate before executing, every time.
    validation = validate_sql(connection, sql_text, question_text)
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail={"errors": validation["errors"]})

    execution = execute_query(
        connection, validation["final_sql"], row_cap=EXECUTE_ROW_CAP,
        statement_timeout_ms=EXECUTE_STATEMENT_TIMEOUT_MS,
    )
    executions_total.inc()

    return ExecuteResponse(
        columns=execution["columns"],
        rows=[list(row) for row in execution["rows"]],
        row_count=len(execution["rows"]),
    )
