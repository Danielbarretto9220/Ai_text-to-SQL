"""
Application-wide settings (API/service config, not DB connection details —
see app/db/session.py for that).

See enterprise-text-to-sql-architecture.md §6.3, §6.5.
"""

import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")


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
