"""
FastAPI application entrypoint.

Loads the embedding model and cross-encoder reranker once at startup via
lifespan, not per-request — each takes several seconds to load, so
per-request loading would make every API call unusably slow. Routes
access them via request.app.state.embedding_model / .reranker_model.

Run: uvicorn app.main:app --host <API_HOST> --port <API_PORT>

See enterprise-text-to-sql-architecture.md §6.3, §6.4.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import LOG_LEVEL
from app.retrieval.rerank import load_reranker_model
from app.retrieval.vector_search import load_embedding_model

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Loading embedding and reranker models...")
    app.state.embedding_model = load_embedding_model()
    app.state.reranker_model = load_reranker_model()
    logger.info("Models loaded. Ready to serve.")
    yield
    logger.info("Shutting down.")


app = FastAPI(
    title="Banking Text-to-SQL API",
    description="Natural-language to SQL for the banking loans warehouse.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],  # Streamlit's default port
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})


from app.api import routes_admin, routes_feedback, routes_query  # noqa: E402

app.include_router(routes_query.router, prefix="/api/v1", tags=["query"])
app.include_router(routes_feedback.router, prefix="/api/v1", tags=["feedback"])
app.include_router(routes_admin.router, tags=["admin"])
