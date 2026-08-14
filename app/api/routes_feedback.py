"""
POST /api/v1/feedback — user marks a generated query correct/incorrect,
optionally with a correction. Feeds meta.query_patterns (§10 few-shot bank).

See enterprise-text-to-sql-architecture.md §6.4.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_db
from app.api.metrics import feedback_submitted_total
from app.api.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter()


def _promote_to_pattern(connection, query_id, corrected_sql):
    """Promote a logged query into meta.query_patterns — the existing
    few-shot bank consumed by hybrid_search/prompt_builder. Explicit
    only (the `promote` flag), never an automatic side effect of a
    thumbs-up: silently mutating the few-shot bank that drives future
    retrieval quality shouldn't happen without the caller asking for it.
    """

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT question, generated_sql, tables_used FROM meta.query_log WHERE query_id = %s;",
            (query_id,),
        )
        row = cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"No query_log row for query_id={query_id}.")

    question, generated_sql, tables_used = row
    sql_template = corrected_sql or generated_sql

    if not sql_template:
        raise HTTPException(status_code=400, detail="Nothing to promote: no corrected_sql and no generated_sql.")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO meta.query_patterns (intent_description, example_question, sql_template, tables_used)
            VALUES (%s, %s, %s, %s)
            RETURNING pattern_id;
            """,
            (f"Promoted from feedback on query_id={query_id}", question, sql_template, tables_used),
        )
        pattern_id = cursor.fetchone()[0]

    return pattern_id


@router.post("/feedback", response_model=FeedbackResponse)
def post_feedback(payload: FeedbackRequest, connection=Depends(get_db)):
    feedback_submitted_total.labels(is_correct=str(payload.is_correct)).inc()

    promoted_to_pattern_id = None
    if payload.promote:
        promoted_to_pattern_id = _promote_to_pattern(connection, payload.query_id, payload.corrected_sql)

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO meta.query_feedback
                (query_id, is_correct, corrected_sql, comment, promoted_to_pattern_id)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING feedback_id;
            """,
            (payload.query_id, payload.is_correct, payload.corrected_sql, payload.comment, promoted_to_pattern_id),
        )
        feedback_id = cursor.fetchone()[0]

    connection.commit()

    return FeedbackResponse(feedback_id=feedback_id, promoted_to_pattern_id=promoted_to_pattern_id)
