"""
Application-wide settings (API/service config, not DB connection details —
see app/db/session.py for that).

See enterprise-text-to-sql-architecture.md §6.3, §6.5.
"""

import os

from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Tiered model selection (app/llm/client.py): GROQ_MODEL handles the first
# attempt on every call — smaller/faster, sufficient for the large majority
# of well-scoped text-to-SQL questions. GROQ_ESCALATION_MODEL is only
# reached by call_llm()'s one automatic repair retry, when the first
# model's response failed validation.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_ESCALATION_MODEL = os.getenv("GROQ_ESCALATION_MODEL", "openai/gpt-oss-120b")


def _env_bool(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8000"))
API_BASE_URL = os.getenv("API_BASE_URL", f"http://{API_HOST}:{API_PORT}")

# Feature flag for app/pipeline.py's execute_query() — the only code path
# in this project that runs LLM-generated SQL against the real database.
# Defaults off; must be explicitly enabled via .env.
EXECUTE_ENABLED = _env_bool("EXECUTE_ENABLED", False)
EXECUTE_ROW_CAP = int(os.getenv("EXECUTE_ROW_CAP", "1000"))
EXECUTE_STATEMENT_TIMEOUT_MS = int(os.getenv("EXECUTE_STATEMENT_TIMEOUT_MS", "5000"))

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
