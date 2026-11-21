"""Router tests use fake chat models: no keys, no network."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_catalog import ModelInfo, family_of
from archoptimize.llm.model_router import (
    AllModelsFailedError,
    Candidate,
    ModelRouter,
    NoModelAvailableError,
)
from archoptimize.llm.role_config import load_settings

KEYS_BOTH = ProviderKeys.from_values("gsk_" + "x" * 40, "sk-or-v1-" + "y" * 40)
KEYS_GROQ_ONLY = ProviderKeys.from_values("gsk_" + "x" * 40, None)

GROQ_LIVE_MODELS = [
    ModelInfo(id="openai/gpt-oss-120b", context_length=131_000),
    ModelInfo(id="qwen/qwen3-32b", context_length=131_000),
    ModelInfo(id="meta-llama/llama-prompt-guard-2-86m", context_length=512),
    ModelInfo(id="whisper-large-v3", owner="OpenAI", context_length=448),
    ModelInfo(id="allam-2-7b", owner="SDAIA", context_length=4096),  # too small for the Critic
]


class Reply(BaseModel):
    text: str


class HttpError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class FakeChat:
    """Minimal stand-in for a LangChain chat model."""

    def __init__(self, behaviour: object):
        self.behaviour = behaviour  # "ok" or an Exception to raise

    def _respond(self) -> str:
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return "reply"

    def invoke(self, _input, **_kwargs):
        return self._respond()

    async def ainvoke(self, _input, **_kwargs):
        return self._respond()

    def with_structured_output(self, schema, method, include_raw=False):
        chat = self

        class _Raw:
            usage_metadata = {"total_tokens": 42}

        class _Structured:
            def invoke(self, _input, **_kwargs):
                chat._respond()
                if chat.behaviour == "bad-json":
                    return {"raw": _Raw(), "parsed": None, "parsing_error": ValueError("bad")}
                parsed = schema(text=method)  # echo the method so tests can check it
                return {"raw": _Raw(), "parsed": parsed, "parsing_error": None}

        return _Structured()


@pytest.fixture
def make_router(openrouter_models):
    def _make(failures: dict[str, Exception] | None = None) -> ModelRouter:
        failures = failures or {}
        return ModelRouter(
            load_settings(),
            chat_factory=lambda c, _keys: FakeChat(failures.get(c.model, "ok")),
            openrouter_fetch=lambda: openrouter_models,
            groq_fetch=lambda _key: GROQ_LIVE_MODELS,
        )

    return _make


def test_groq_role_tries_groq_models_then_openrouter_fallback(make_router):
    candidates = make_router().candidates_for("architect", KEYS_BOTH)
    assert candidates[:2] == [
        Candidate("groq", "openai/gpt-oss-120b"),
        Candidate("groq", "openai/gpt-oss-20b"),
    ]
    fallbacks = candidates[2:]
    assert 1 <= len(fallbacks) <= 3
    assert all(c.provider == "openrouter" for c in fallbacks)


def test_critic_is_a_different_family_from_architect(make_router):
    candidates = make_router().candidates_for("critic", KEYS_BOTH)
    assert candidates
    assert all(family_of(c.model) != "openai" for c in candidates)


def test_critic_without_openrouter_uses_another_groq_family(make_router):
    candidates = make_router().candidates_for("critic", KEYS_GROQ_ONLY)
    assert [c.model for c in candidates] == ["qwen/qwen3-32b"]  # not openai, guard or whisper
    assert candidates[0].structured_method == "function_calling"


def test_no_keys_gives_a_clear_error(make_router):
    llm = make_router().get_llm("reviewer", ProviderKeys())
    with pytest.raises(NoModelAvailableError):
        llm.invoke("hi")


def test_failed_model_is_skipped_and_put_on_cooldown(make_router):
    router = make_router({"openai/gpt-oss-120b": HttpError(429)})
    llm = router.get_llm("architect", KEYS_GROQ_ONLY)

    assert llm.invoke("hi") == "reply"
    assert llm.last_candidate.model == "openai/gpt-oss-20b"
    # the next request starts with 20b because 120b is cooling down
    assert router.candidates_for("architect", KEYS_GROQ_ONLY)[0].model == "openai/gpt-oss-20b"


def test_auth_error_skips_rest_of_provider(make_router):
    router = make_router({"openai/gpt-oss-120b": HttpError(401)})
    llm = router.get_llm("architect", KEYS_BOTH)
    llm.invoke("hi")
    assert llm.last_candidate.provider == "openrouter"


def test_all_failures_raise_a_summary_without_keys(make_router):
    secret = "gsk_" + "z" * 40
    router = make_router()
    router._chat_factory = lambda _c, _keys: FakeChat(RuntimeError(f"boom {secret}"))
    llm = router.get_llm("reviewer", KEYS_BOTH)

    with pytest.raises(AllModelsFailedError) as err:
        llm.invoke("hi")
    assert secret not in str(err.value)
    assert "[redacted-key]" in str(err.value)


def test_structured_output_uses_the_candidates_method_and_reports_tokens(make_router):
    llm = make_router().get_llm("reviewer", KEYS_GROQ_ONLY).with_structured_output(Reply)
    assert llm.invoke("hi") == Reply(text="json_schema")
    assert llm.last_tokens == 42


def test_output_that_does_not_fit_the_schema_tries_next_model(make_router):
    router = make_router({"openai/gpt-oss-120b": "bad-json"})
    llm = router.get_llm("architect", KEYS_GROQ_ONLY).with_structured_output(Reply)
    assert llm.invoke("hi") == Reply(text="json_schema")
    assert llm.last_candidate.model == "openai/gpt-oss-20b"


def test_async_invoke_falls_back_too(make_router):
    llm = make_router({"openai/gpt-oss-120b": HttpError(503)}).get_llm("chair", KEYS_GROQ_ONLY)
    assert asyncio.run(llm.ainvoke("hi")) == "reply"
    assert llm.last_candidate.model == "openai/gpt-oss-20b"


def test_unknown_role_is_rejected(make_router):
    with pytest.raises(ValueError, match="unknown role"):
        make_router().candidates_for("nope", KEYS_BOTH)
