"""Build an OpenRouter chat model.

OpenRouter speaks the OpenAI API, so we reuse LangChain's ChatOpenAI and only change the
base URL. Retries are kept low: on failure the router moves to the next free model instead.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from archoptimize.llm.role_config import OpenRouterSettings


def make_openrouter_chat(
    model: str, api_key: SecretStr, settings: OpenRouterSettings, temperature: float = 0.2
) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=settings.base_url,
        max_retries=settings.max_retries,
        timeout=settings.timeout_seconds,
        temperature=temperature,
        default_headers={"X-Title": settings.app_title},
    )
