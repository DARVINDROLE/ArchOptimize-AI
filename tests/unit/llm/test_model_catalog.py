from __future__ import annotations

import httpx
import respx

from archoptimize.llm.model_catalog import (
    CachedCatalog,
    ModelInfo,
    family_of,
    fetch_openrouter_models,
    parse_groq_models,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/models"


def test_fetch_parses_catalog_and_detects_free_models(openrouter_catalog_payload):
    with respx.mock:
        respx.get(OPENROUTER_URL).mock(
            return_value=httpx.Response(200, json=openrouter_catalog_payload)
        )
        models = {m.id: m for m in fetch_openrouter_models(OPENROUTER_URL)}

    assert models["qwen/qwen3-big:free"].is_free
    assert not models["anthropic/paid-model"].is_free
    assert not models["openrouter/auto"].is_free  # meta-router: family unknown
    assert models["google/gemma-vision:free"].input_modalities == ["text", "image"]


def test_family_of():
    assert family_of("openai/gpt-oss-20b") == "openai"
    assert family_of("llama-3.3-70b-versatile", owner="Meta") == "meta"


def test_groq_parse_skips_inactive_models():
    payload = {"data": [{"id": "a/x", "context_window": 1000}, {"id": "b/y", "active": False}]}
    assert [m.id for m in parse_groq_models(payload)] == ["a/x"]


def test_cache_respects_ttl(fake_clock):
    cache = CachedCatalog(ttl_seconds=3600, clock=fake_clock)
    calls = []

    def fetch():
        calls.append(1)
        return [ModelInfo(id="a/b")]

    cache.get(fetch)
    cache.get(fetch)
    assert len(calls) == 1  # second call served from cache

    fake_clock.now = 3601
    cache.get(fetch)
    assert len(calls) == 2  # expired, so fetched again


def test_cache_returns_stale_list_when_refresh_fails(fake_clock):
    cache = CachedCatalog(ttl_seconds=10, clock=fake_clock)
    cache.get(lambda: [ModelInfo(id="a/b")])
    fake_clock.now = 999

    def broken():
        raise httpx.ConnectError("down")

    assert [m.id for m in cache.get(broken)] == ["a/b"]
