"""
Full user journey: POST /api/v1/query -> POST /api/v1/execute ->
POST /api/v1/feedback with promotion. One live Groq call.

EXECUTE_ENABLED defaults to false (app/config.py), so the /execute step
is monkeypatched on for this test only — patching
app.api.routes_query.EXECUTE_ENABLED directly, since routes_query.py
imports the constant by value at module load time
(`from app.config import EXECUTE_ENABLED`), so patching app.config's own
copy after import wouldn't be seen by the already-bound name in the
route module.
"""

import pytest

from tests.conftest import retry_on_5xx


@pytest.mark.live
def test_full_query_execute_feedback_journey(api_client, db_connection, monkeypatch):
    monkeypatch.setattr("app.api.routes_query.EXECUTE_ENABLED", True)

    query_id = None
    promoted_pattern_id = None

    try:
        query_response = retry_on_5xx(
            lambda: api_client.post(
                "/api/v1/query", json={"question": "List customers with overdue EMI payments"}
            )
        )
        assert query_response.status_code == 200, query_response.text
        query_body = query_response.json()
        query_id = query_body["query_id"]
        assert query_body["valid"] is True

        execute_response = api_client.post("/api/v1/execute", json={"query_id": query_id})
        assert execute_response.status_code == 200, execute_response.text
        assert execute_response.json()["columns"]

        feedback_response = api_client.post(
            "/api/v1/feedback",
            json={"query_id": query_id, "is_correct": True, "promote": True, "comment": "e2e test"},
        )
        assert feedback_response.status_code == 200
        feedback_body = feedback_response.json()
        promoted_pattern_id = feedback_body["promoted_to_pattern_id"]
        assert promoted_pattern_id is not None

        with db_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pattern_id FROM meta.query_patterns WHERE pattern_id = %s;", (promoted_pattern_id,)
            )
            assert cursor.fetchone() is not None

    finally:
        with db_connection.cursor() as cursor:
            if promoted_pattern_id is not None:
                cursor.execute(
                    "DELETE FROM meta.document_embeddings WHERE document_id = %s;",
                    (f"query_pattern:{promoted_pattern_id}",),
                )
                cursor.execute(
                    "DELETE FROM meta.query_feedback WHERE promoted_to_pattern_id = %s;", (promoted_pattern_id,)
                )
                cursor.execute("DELETE FROM meta.query_patterns WHERE pattern_id = %s;", (promoted_pattern_id,))
            if query_id is not None:
                cursor.execute("DELETE FROM meta.query_feedback WHERE query_id = %s;", (query_id,))
                cursor.execute("DELETE FROM meta.query_log WHERE query_id = %s;", (query_id,))
        db_connection.commit()
