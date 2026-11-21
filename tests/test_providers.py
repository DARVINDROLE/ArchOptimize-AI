"""Provider layer tests: no keys, no network (HTTP is mocked with respx, LLMs are fakes)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx
from pydantic import BaseModel

from arb.providers.config import RoleRequirements, load_settings
from arb.providers.cooldown import Cooldown
from arb.providers.keys import ProviderKeys, redact
from arb.providers.model_catalog import (
    CachedCatalog,
    ModelInfo,
    family_of,
    fetch_openrouter_models,
    parse_groq_models,
)
from arb.providers.router import (
    AllModelsFailedError,
    Candidate,
    ModelRouter,
    NoModelAvailableError,
)
from arb.providers.selector import select_models

OPENROUTER_URL = "https://openrouter.ai/api/v1/models"


def or_model(id, *, ctx=128_000, image=False, params=("structured_outputs", "tools"), price="0"):
    return {
        "id": id,
        "name": id,
        "context_length": ctx,
        "architecture": {
            "input_modalities": ["text", "image"] if image else ["text"],
            "output_modalities": ["text"],
        },
        "pricing": {"prompt": price, "completion": price},
        "supported_parameters": list(params),
    }


CATALOG = {
    "data": [
        or_model("qwen/qwen3-big:free", ctx=262_000),
        or_model("google/gemma-vision:free", ctx=96_000, image=True),
        or_model("openai/gpt-oss-120b:free", ctx=131_000),
        or_model("mistral/small-json-mode:free", params=("response_format",)),
        or_model("meta-llama/tiny:free", ctx=8_000),
        or_model("anthropic/paid-model", price="0.000003"),
        or_model("openrouter/auto", price="-1"),
    ]
}


def models() -> list[ModelInfo]:
    with respx.mock:
        respx.get(OPENROUTER_URL).mock(return_value=httpx.Response(200, json=CATALOG))
        return fetch_openrouter_models(OPENROUTER_URL)


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


# ---------------- catalog ----------------


def test_parse_and_free_detection():
    ms = {m.id: m for m in models()}
    assert ms["qwen/qwen3-big:free"].is_free
    assert not ms["anthropic/paid-model"].is_free
    assert not ms["openrouter/auto"].is_free  # meta-router: unknown family
    assert ms["google/gemma-vision:free"].input_modalities == ["text", "image"]


def test_family_of():
    assert family_of("openai/gpt-oss-20b") == "openai"
    assert family_of("llama-3.3-70b-versatile", owner="Meta") == "meta"


def test_groq_parse_skips_inactive():
    payload = {"data": [{"id": "a/x", "context_window": 1000}, {"id": "b/y", "active": False}]}
    assert [m.id for m in parse_groq_models(payload)] == ["a/x"]


def test_cache_ttl_and_stale_fallback():
    clock = FakeClock()
    cache = CachedCatalog(ttl_seconds=3600, clock=clock)
    calls = []

    def fetch():
        calls.append(1)
        return [ModelInfo(id="a/b")]

    cache.get(fetch)
    cache.get(fetch)
    assert len(calls) == 1  # cached
    clock.t = 3601
    cache.get(fetch)
    assert len(calls) == 2  # expired -> refetched

    clock.t = 99999

    def broken():
        raise httpx.ConnectError("down")

    assert [m.id for m in cache.get(broken)] == ["a/b"]  # stale list beats nothing


# ---------------- selector ----------------


def test_vision_requirements():
    chosen = select_models(models(), RoleRequirements(image_input=True))
    assert [m.id for m in chosen] == ["google/gemma-vision:free"]


def test_structured_output_and_context_filters_and_ranking():
    chosen = select_models(models(), RoleRequirements(min_context=64_000))
    ids = [m.id for m in chosen]
    assert "mistral/small-json-mode:free" not in ids  # JSON mode only, no schema support
    assert "meta-llama/tiny:free" not in ids  # context too small
    assert "anthropic/paid-model" not in ids  # not free
    assert ids[0] == "qwen/qwen3-big:free"  # largest context first


def test_family_exclusion_prefer_cooldown_and_limit():
    req = RoleRequirements(min_context=64_000)
    assert "openai/gpt-oss-120b:free" not in [
        m.id for m in select_models(models(), req, exclude_families={"openai"})
    ]
    assert select_models(models(), req, prefer=["gemma"])[0].id == "google/gemma-vision:free"
    cooling = select_models(models(), req, is_cooling=lambda i: i.startswith("qwen"))
    assert all(not m.id.startswith("qwen") for m in cooling)
    assert len(select_models(models(), req, limit=1)) == 1


# ---------------- keys ----------------


def test_keys_hidden_and_placeholders_ignored():
    keys = ProviderKeys.from_values("gsk_" + "a" * 40, "sk-or-v1-your_key_here")
    assert keys.openrouter is None
    assert "gsk_" not in repr(keys) and "gsk_" not in str(keys)
    assert redact("bad key gsk_" + "b" * 30 + " here") == "bad key [redacted-key] here"


# ---------------- router ----------------


class Reply(BaseModel):
    text: str


class FakeChat:
    """Minimal stand-in for a LangChain chat model."""

    def __init__(self, behaviour):
        self.behaviour = behaviour  # "ok" | Exception

    def _go(self):
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return "reply"

    def invoke(self, _input, **_kw):
        return self._go()

    async def ainvoke(self, _input, **_kw):
        return self._go()

    def with_structured_output(self, schema, method):
        outer = self

        class _S:
            def invoke(self, _input, **_kw):
                outer._go()
                return schema(text=method)

        return _S()


class HttpError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


KEYS_BOTH = ProviderKeys.from_values("gsk_" + "x" * 40, "sk-or-v1-" + "y" * 40)
KEYS_GROQ = ProviderKeys.from_values("gsk_" + "x" * 40, None)

GROQ_LIVE = [
    ModelInfo(id="openai/gpt-oss-120b", context_length=131_000),
    ModelInfo(id="qwen/qwen3-32b", context_length=131_000),
    ModelInfo(id="meta-llama/llama-prompt-guard-2-86m", context_length=512),
    ModelInfo(id="whisper-large-v3", owner="OpenAI", context_length=448),
]


def make_router(behaviours: dict[str, object] | None = None) -> ModelRouter:
    behaviours = behaviours or {}
    return ModelRouter(
        load_settings(),
        chat_factory=lambda c, _k: FakeChat(behaviours.get(c.model, "ok")),
        openrouter_fetch=models,
        groq_fetch=lambda _key: GROQ_LIVE,
    )


def test_groq_role_candidates_then_openrouter_fallback():
    cands = make_router().candidates_for("architect", KEYS_BOTH)
    assert cands[:2] == [
        Candidate("groq", "openai/gpt-oss-120b"),
        Candidate("groq", "openai/gpt-oss-20b"),
    ]
    assert all(c.provider == "openrouter" for c in cands[2:])
    assert 1 <= len(cands[2:]) <= 3


def test_critic_is_different_family_from_architect():
    cands = make_router().candidates_for("critic", KEYS_BOTH)
    assert cands and all(family_of(c.model) != "openai" for c in cands)


def test_critic_without_openrouter_uses_other_groq_family():
    cands = make_router().candidates_for("critic", KEYS_GROQ)
    assert [c.model for c in cands] == ["qwen/qwen3-32b"]  # not openai, not guard/whisper
    assert cands[0].structured_method == "function_calling"


def test_no_keys_means_clear_error():
    llm = make_router().get_llm("reviewer", ProviderKeys())
    with pytest.raises(NoModelAvailableError):
        llm.invoke("hi")


def test_falls_back_and_puts_failed_model_on_cooldown():
    router = make_router({"openai/gpt-oss-120b": HttpError(429)})
    llm = router.get_llm("architect", KEYS_GROQ)
    assert llm.invoke("hi") == "reply"
    assert llm.last_candidate.model == "openai/gpt-oss-20b"
    # next request skips the cooling 120b model
    assert router.candidates_for("architect", KEYS_GROQ)[0].model == "openai/gpt-oss-20b"


def test_auth_error_skips_rest_of_provider_and_moves_to_openrouter():
    router = make_router({"openai/gpt-oss-120b": HttpError(401)})
    llm = router.get_llm("architect", KEYS_BOTH)
    llm.invoke("hi")
    assert llm.last_candidate.provider == "openrouter"


def test_all_fail_raises_with_redacted_summary():
    secret = "gsk_" + "z" * 40
    router = make_router({"openai/gpt-oss-20b": HttpError(500)})
    router._chat_factory = lambda c, _k: FakeChat(RuntimeError(f"boom {secret}"))
    llm = router.get_llm("reviewer", KEYS_BOTH)
    with pytest.raises(AllModelsFailedError) as err:
        llm.invoke("hi")
    assert secret not in str(err.value)
    assert "[redacted-key]" in str(err.value)


def test_structured_output_uses_candidate_method():
    llm = make_router().get_llm("reviewer", KEYS_GROQ).with_structured_output(Reply)
    assert llm.invoke("hi") == Reply(text="json_schema")


def test_async_invoke():
    llm = make_router({"openai/gpt-oss-120b": HttpError(503)}).get_llm("chair", KEYS_GROQ)
    assert asyncio.run(llm.ainvoke("hi")) == "reply"
    assert llm.last_candidate.model == "openai/gpt-oss-20b"


def test_cooldown_expires():
    clock = FakeClock()
    cd = Cooldown(60, clock=clock)
    cd.mark("m")
    assert cd.is_cooling("m")
    clock.t = 61
    assert not cd.is_cooling("m")


def test_unknown_role():
    with pytest.raises(ValueError, match="unknown role"):
        make_router().candidates_for("nope", KEYS_BOTH)
