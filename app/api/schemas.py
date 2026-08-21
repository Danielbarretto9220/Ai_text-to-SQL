"""
Pydantic request/response models for the FastAPI layer. Distinct from
app/llm/schemas.py, which models the LLM's own structured output — these
model what the HTTP API itself accepts and returns.

See enterprise-text-to-sql-architecture.md §6.4.
"""

from typing import Optional

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1)
    execute: bool = False


class ConfidenceInfo(BaseModel):
    score: float
    label: str


class CostInfo(BaseModel):
    total_cost: float
    plan_rows: int


class QueryResponse(BaseModel):
    """query_id is the contract POST /api/v1/feedback depends on — every
    successful call writes a meta.query_log row and returns its id."""

    query_id: int
    question: str
    sql: Optional[str] = None
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tables_used: list[str] = Field(default_factory=list)
    llm_confidence: Optional[str] = None
    retrieval_confidence: Optional[ConfidenceInfo] = None
    cost: Optional[CostInfo] = None
    retried_for_validation: bool = False
    columns: Optional[list[str]] = None
    results: Optional[list[list]] = None
    selected_tables: list[dict] = Field(default_factory=list)
    join_paths: list[dict] = Field(default_factory=list)


class ExecuteRequest(BaseModel):
    """Either query_id (preferred — looks up the logged sql/question) or
    sql (+ optional question, for NL-intent business rules) directly.
    The SQL is always re-validated server-side before execution — never
    trust a client-supplied string just because an earlier response
    contained it."""

    query_id: Optional[int] = None
    sql: Optional[str] = None
    question: Optional[str] = None


class ExecuteResponse(BaseModel):
    columns: list[str]
    rows: list[list]
    row_count: int


class FeedbackRequest(BaseModel):
    query_id: int
    is_correct: bool
    corrected_sql: Optional[str] = None
    comment: Optional[str] = None
    promote: bool = False


class FeedbackResponse(BaseModel):
    feedback_id: int
    promoted_to_pattern_id: Optional[int] = None


class SchemaSearchResult(BaseModel):
    document_id: str
    document_type: str
    content: str
    score: float


class SchemaSearchResponse(BaseModel):
    query: str
    results: list[SchemaSearchResult]


class ReindexResponse(BaseModel):
    embedded: list[str]
    unchanged: int
    deleted: list[str]


class HealthResponse(BaseModel):
    status: str
    database: bool
    models_loaded: bool
    groq_api_key_configured: bool
