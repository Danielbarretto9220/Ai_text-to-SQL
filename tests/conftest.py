"""
Shared fixtures. All tests hit the real database (and the `live`-marked
ones hit the real Groq API too) — chosen deliberately over mocking, per
docs/API_AND_TESTING_PLAN.md.

Model-loading fixtures (embedding_model, reranker_model) and db_connection
are session-scoped: reloading the MiniLM embedding model + cross-encoder
reranker per test would add minutes to a run, mirroring why app/main.py's
lifespan loads them once at startup rather than per-request.

db_transaction is function-scoped and rolls back after each test, but it
only isolates tests that don't call connection.commit() themselves.
app/api/routes_query.py and routes_feedback.py commit their
meta.query_log/meta.query_feedback writes internally (a query_id has to be
durably assigned so a later request can look it up), so a wrapping
rollback can't undo those specific writes. Tests that exercise those
routes (test_api.py, test_e2e.py) track the ids they create and delete
them explicitly in a finally block instead — see their own fixtures.
"""

import time

import pytest
from fastapi.testclient import TestClient
from openai import InternalServerError

from app.api.deps import get_db
from app.db.session import get_connection
from app.retrieval.rerank import load_reranker_model
from app.retrieval.vector_search import load_embedding_model


def pytest_configure(config):
    config.addinivalue_line("markers", "live: test makes a real Groq API call (free-tier rate-limited, non-deterministic)")
    config.addinivalue_line("markers", "slow: test is slow to run")


@pytest.fixture(scope="session")
def db_connection():
    connection = get_connection()
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def embedding_model():
    return load_embedding_model()


@pytest.fixture(scope="session")
def reranker_model():
    return load_reranker_model()


@pytest.fixture
def db_transaction():
    """A dedicated connection, rolled back after the test. See module
    docstring for the caveat on routes that commit internally."""

    connection = get_connection()
    yield connection
    connection.rollback()
    connection.close()


@pytest.fixture(scope="session")
def api_client():
    """FastAPI TestClient. Used as a context manager so the app's own
    lifespan runs (loading its own embedding/reranker models onto
    app.state, exactly as it would in production) — session-scoped so
    that startup cost is paid once, not per test.

    get_db is overridden to hand out a single long-lived connection
    (rather than a fresh one per request via app/db/session.get_connection())
    so tests can inspect what a request wrote without a second connection
    racing it."""

    from app.main import app

    test_connection = get_connection()

    def _get_db_override():
        yield test_connection

    app.dependency_overrides[get_db] = _get_db_override

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
    test_connection.close()


def retry_on_api_error(func, retries=2, delay=5):
    """Retries func() on openai.InternalServerError (transient 5xx from
    Groq's OpenAI-compatible endpoint). Deliberately does NOT retry
    openai.RateLimitError (429) — that was a hard-learned lesson from this
    project's earlier Gemini integration, where a 429 quota error looked
    superficially retryable (the SDK's own short RetryInfo hint) but was
    actually a daily cap that no amount of retrying fixes; Groq's free tier
    has the same shape of hard rate limits. For direct
    call_llm()/generate_validated_sql() calls, where the exception
    propagates to the caller."""

    last_exc = None
    for attempt in range(retries + 1):
        try:
            return func()
        except InternalServerError as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(delay)
    raise last_exc


def retry_on_5xx(func, retries=2, delay=5):
    """Like retry_on_api_error, but for calls made through the FastAPI
    TestClient: app/main.py's blanket exception handler catches any
    exception (including openai SDK errors) and turns it into an HTTP 500
    JSON response before it ever reaches the test process as a raised
    exception, so retrying has to inspect response.status_code instead
    of catching an exception."""

    response = None
    for attempt in range(retries + 1):
        response = func()
        if response.status_code < 500:
            return response
        if attempt < retries:
            time.sleep(delay)
    return response
