"""Real API calls. Skipped by default; run with:  uv run python -m pytest -m live
Needs GROQ_API_KEY (and OPENROUTER_API_KEY for the OpenRouter test) in .env.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import get_router

pytestmark = pytest.mark.live


class Ping(BaseModel):
    ok: bool
    word: str


@pytest.fixture(scope="module")
def keys() -> ProviderKeys:
    keys = ProviderKeys.from_env()
    if keys.groq is None:
        pytest.skip("GROQ_API_KEY not set")
    return keys


def test_groq_structured_output(keys):
    llm = get_router().get_llm("architect", keys, only_provider="groq")
    result = llm.with_structured_output(Ping).invoke("Return ok=true and word='pong'.")
    assert result.ok is True


def test_openrouter_fallback_text_reply(keys):
    if keys.openrouter is None:
        pytest.skip("OPENROUTER_API_KEY not set")
    llm = get_router().get_llm("reviewer", keys, only_provider="openrouter")
    reply = llm.invoke("Reply with exactly: ok")
    assert reply.content
