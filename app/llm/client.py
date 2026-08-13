"""
Provider-agnostic LLM client wrapper (Anthropic/OpenAI/Azure OpenAI/
on-prem vLLM), swappable via app/config.py so the backend can change
without touching callers.

Not yet implemented — see enterprise-text-to-sql-architecture.md §6.5, §8.
"""
