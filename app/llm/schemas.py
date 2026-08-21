"""
Pydantic response models for the LLM's structured JSON output
({ sql, tables_used, assumptions, confidence }) used to validate and
parse the model response, with one automatic repair retry on failure.

One schema covers both branches of the seeded system prompt's contract
(meta.prompt_versions, prompt_name="text_to_sql_system_prompt", rule 1):
a normal SQL-generation response, or an
{"error": "insufficient_context", "missing": "..."} response when CONTEXT
doesn't have what's needed. app/llm/client.py's JSON-Object-mode call to
Groq doesn't lock the model into one schema (Groq's JSON Schema strict mode
was tried and found unreliable for this schema's nullable fields — see
app/llm/client.py's docstring), so this model still has to represent both
branches in a single shape — every field is optional and callers branch on
is_error_response(), with parse/validation failures caught by
call_llm()'s repair retry rather than prevented at generation time.

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
