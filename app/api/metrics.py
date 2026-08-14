"""
Prometheus counters/histogram, incremented from the routes (not threaded
through the pipeline internals). Exposed at GET /metrics by
routes_admin.py — not under /api/v1/, per architecture doc §6.4.
"""

from prometheus_client import Counter, Histogram

queries_generated_total = Counter("queries_generated_total", "Total questions sent to POST /api/v1/query")
validation_failures_total = Counter(
    "validation_failures_total", "Total queries that failed validation (after any repair retry)"
)
llm_repair_retries_total = Counter(
    "llm_repair_retries_total", "Total times the one validation-failure repair retry was triggered"
)
executions_total = Counter("executions_total", "Total queries actually executed via execute_query()")
feedback_submitted_total = Counter(
    "feedback_submitted_total", "Total feedback submissions", ["is_correct"]
)

query_latency_seconds = Histogram(
    "query_latency_seconds", "End-to-end latency of POST /api/v1/query (retrieval -> validate)"
)
