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
