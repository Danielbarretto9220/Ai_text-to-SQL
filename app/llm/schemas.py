"""
Pydantic response models for the LLM's structured JSON output
({ sql, tables_used, assumptions, confidence }) used to validate and
parse the model response, with one automatic repair retry on failure.

Not yet implemented — see enterprise-text-to-sql-architecture.md §3.4.
"""
