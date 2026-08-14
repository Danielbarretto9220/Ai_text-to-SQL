"""
Shared FastAPI dependencies.

get_db() opens a connection per request via app/db/session.get_connection()
and closes it in a finally — connection pooling is a known future
improvement, not built here.

The embedding/reranker models are NOT dependencies here (they're loaded
once at startup in app/main.py's lifespan and stored on app.state) —
routes access them via the injected Request object
(request.app.state.embedding_model / .reranker_model) to avoid a
circular import between this package and app.main.
"""

from app.db.session import get_connection


def get_db():
    connection = get_connection()
    try:
        yield connection
    finally:
        connection.close()
