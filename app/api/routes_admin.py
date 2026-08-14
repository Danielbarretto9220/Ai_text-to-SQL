"""
GET /api/v1/schema/search, POST /api/v1/admin/reindex,
GET /api/v1/health, GET /metrics.

See enterprise-text-to-sql-architecture.md §6.4.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.deps import get_db
from app.api.schemas import HealthResponse, ReindexResponse, SchemaSearchResponse, SchemaSearchResult
from app.config import GEMINI_API_KEY
from app.retrieval.hybrid_search import hybrid_search
from workers.reindex_embeddings import incremental_reindex

router = APIRouter()


@router.get("/api/v1/health", response_model=HealthResponse)
def health(request: Request, connection=Depends(get_db)):
    """DB reachable, models loaded, API key configured. Never makes a
    live Gemini call — health checks get polled, and polling should
    never bill an external API."""

    database_ok = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            database_ok = cursor.fetchone() == (1,)
    except Exception:
        database_ok = False

    models_loaded = (
        getattr(request.app.state, "embedding_model", None) is not None
        and getattr(request.app.state, "reranker_model", None) is not None
    )

    return HealthResponse(
        status="ok" if (database_ok and models_loaded) else "degraded",
        database=database_ok,
        models_loaded=models_loaded,
        gemini_api_key_configured=bool(GEMINI_API_KEY),
    )


@router.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@router.get("/api/v1/schema/search", response_model=SchemaSearchResponse)
def schema_search(q: str, request: Request, connection=Depends(get_db)):
    """Debug endpoint for retrieval testing — the raw hybrid_search()
    ranking, not the full retrieve_context() pipeline (no rerank/
    relationship-expansion/confidence-scoring layered on top)."""

    results = hybrid_search(connection, q, request.app.state.embedding_model, top_k=10)

    return SchemaSearchResponse(
        query=q,
        results=[
            SchemaSearchResult(
                document_id=r["document_id"],
                document_type=r["document_type"],
                content=r["content"],
                score=r["rrf_score"],
            )
            for r in results
        ],
    )


@router.post("/api/v1/admin/reindex", response_model=ReindexResponse)
def admin_reindex(connection=Depends(get_db)):
    result = incremental_reindex(connection)
    return ReindexResponse(**result)
