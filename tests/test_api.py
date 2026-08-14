"""
FastAPI routes via TestClient — one live call backs the module-scoped
logged_query fixture (POST /api/v1/query); everything else exercises the
API surface without touching Gemini.

Writes go through app/api/routes_query.py and routes_feedback.py, which
commit internally (see conftest.py's module docstring for why that means
tests clean up explicitly rather than relying on transaction rollback).
"""

import pytest

from tests.conftest import retry_on_5xx


def test_health_does_not_require_live_call(api_client):
    response = api_client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] is True
    assert body["models_loaded"] is True


def test_metrics_endpoint(api_client):
    response = api_client.get("/metrics")
    assert response.status_code == 200
    assert b"queries_generated_total" in response.content


def test_schema_search_endpoint(api_client):
    response = api_client.get("/api/v1/schema/search", params={"q": "overdue loans"})
    assert response.status_code == 200
    assert response.json()["results"]


def test_admin_reindex_endpoint(api_client):
    response = api_client.post("/api/v1/admin/reindex")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"embedded", "unchanged", "deleted"}


def test_execute_returns_403_when_disabled(api_client):
    # EXECUTE_ENABLED defaults to false (app/config.py) and this test
    # doesn't patch it, unlike test_e2e.py's journey test.
    response = api_client.post("/api/v1/execute", json={"sql": "SELECT 1;"})
    assert response.status_code == 403


@pytest.fixture(scope="module")
def logged_query(api_client, db_connection):
    response = retry_on_5xx(
        lambda: api_client.post("/api/v1/query", json={"question": "List customers with overdue EMI payments"})
    )
    assert response.status_code == 200, response.text
    body = response.json()

    yield body

    with db_connection.cursor() as cursor:
        cursor.execute("DELETE FROM meta.query_feedback WHERE query_id = %s;", (body["query_id"],))
        cursor.execute("DELETE FROM meta.query_log WHERE query_id = %s;", (body["query_id"],))
    db_connection.commit()


@pytest.mark.live
def test_query_endpoint_persists_query_log_row(logged_query, db_connection):
    assert logged_query["query_id"] is not None

    with db_connection.cursor() as cursor:
        cursor.execute("SELECT question FROM meta.query_log WHERE query_id = %s;", (logged_query["query_id"],))
        row = cursor.fetchone()
    assert row is not None
    assert row[0] == "List customers with overdue EMI payments"


@pytest.mark.live
def test_query_endpoint_response_shape(logged_query):
    assert logged_query["valid"] is True
    assert logged_query["sql"]
    assert "customers" in logged_query["tables_used"]


@pytest.mark.live
def test_feedback_endpoint(api_client, db_connection, logged_query):
    response = api_client.post(
        "/api/v1/feedback",
        json={"query_id": logged_query["query_id"], "is_correct": True, "comment": "test", "promote": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["feedback_id"] is not None
    assert body["promoted_to_pattern_id"] is None

    with db_connection.cursor() as cursor:
        cursor.execute("DELETE FROM meta.query_feedback WHERE feedback_id = %s;", (body["feedback_id"],))
    db_connection.commit()
