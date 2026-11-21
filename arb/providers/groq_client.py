"""Build a Groq chat model.

Retry on 429 (rate limit): the Groq SDK already retries 429/5xx with exponential backoff
and honours the `retry-after` header; `max_retries` controls how many times.
The 120b -> 20b fallback comes from the order of models in `models.yaml`.
"""

from __future__ import annotations

from langchain_groq import ChatGroq
from pydantic import SecretStr

from arb.providers.config import GroqSettings


def make_groq_chat(
    model: str, api_key: SecretStr, settings: GroqSettings, temperature: float = 0.2
) -> ChatGroq:
    return ChatGroq(
        model=model,
        api_key=api_key,
        max_retries=settings.max_retries,
        timeout=settings.timeout_seconds,
        temperature=temperature,
    )
