"""
Pydantic response models for the LLM's structured JSON output
({ sql, tables_used, assumptions, confidence }) used to validate and
parse the model response, with one automatic repair retry on failure.

One schema covers both branches of the seeded system prompt's contract
(meta.prompt_versions, prompt_name="text_to_sql_system_prompt", rule 1):
a normal SQL-generation response, or an
{"error": "insufficient_context", "missing": "..."} response when CONTEXT
doesn't have what's needed. Gemini's response_schema constrains the model
to exactly one schema, so both branches must be representable in it —
hence every field is optional and callers branch on is_error_response().

See enterprise-text-to-sql-architecture.md §3.4.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SQLGenerationResponse(BaseModel):
    sql: Optional[str] = None
    tables_used: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    confidence: Optional[Literal["high", "medium", "low"]] = None
    error: Optional[Literal["insufficient_context"]] = None
    missing: Optional[str] = None


def is_error_response(response):
    return response.error is not None
