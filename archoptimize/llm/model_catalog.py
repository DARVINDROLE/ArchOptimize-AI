"""Live model lists from OpenRouter and Groq, with an in-memory cache.

Why live? Free OpenRouter models appear and disappear, so we never hard-code their IDs.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, Field


def family_of(model_id: str, owner: str | None = None) -> str:
    """Model family = the vendor part of the id: 'openai/gpt-oss-20b' -> 'openai'.

    Used so the Critic never comes from the same family as the Architect.
    """
    if "/" in model_id:
        return model_id.split("/", 1)[0].lower()
    if owner:
        return owner.lower()
    return model_id.split("-", 1)[0].lower()


class ModelInfo(BaseModel):
    id: str
    name: str = ""
    owner: str | None = None
    context_length: int = 0
    input_modalities: list[str] = Field(default_factory=lambda: ["text"])
    output_modalities: list[str] = Field(default_factory=lambda: ["text"])
    supported_parameters: list[str] = Field(default_factory=list)
    prompt_price: float = -1.0  # USD per token; -1 = unknown
    completion_price: float = -1.0

    @property
    def family(self) -> str:
        return family_of(self.id, self.owner)

    @property
    def is_free(self) -> bool:
        # 'openrouter/...' ids are meta-routers that pick a model for you: their family is
        # unknown, which would break the "Critic family != Architect family" rule.
        if self.id.startswith("openrouter/"):
            return False
        if self.id.endswith(":free"):
            return True
        return self.prompt_price == 0 and self.completion_price == 0


def _price(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return -1.0


def parse_openrouter_models(payload: dict[str, Any]) -> list[ModelInfo]:
    models: list[ModelInfo] = []
    for raw in payload.get("data", []):
        if not raw.get("id"):
            continue
        arch = raw.get("architecture") or {}
        pricing = raw.get("pricing") or {}
        models.append(
            ModelInfo(
                id=raw["id"],
                name=raw.get("name", ""),
                context_length=int(raw.get("context_length") or 0),
                input_modalities=arch.get("input_modalities") or ["text"],
                output_modalities=arch.get("output_modalities") or ["text"],
                supported_parameters=raw.get("supported_parameters") or [],
                prompt_price=_price(pricing.get("prompt")),
                completion_price=_price(pricing.get("completion")),
            )
        )
    return models


def parse_groq_models(payload: dict[str, Any]) -> list[ModelInfo]:
    models: list[ModelInfo] = []
    for raw in payload.get("data", []):
        if not raw.get("id") or raw.get("active") is False:
            continue
        models.append(
            ModelInfo(
                id=raw["id"],
                owner=raw.get("owned_by"),
                context_length=int(raw.get("context_window") or 0),
                prompt_price=0.0,  # free tier with the user's own key
                completion_price=0.0,
            )
        )
    return models


def fetch_openrouter_models(url: str, timeout: float = 15) -> list[ModelInfo]:
    # The OpenRouter model list is public: no key is sent.
    resp = httpx.get(url, timeout=timeout)
    resp.raise_for_status()
    return parse_openrouter_models(resp.json())


def fetch_groq_models(url: str, api_key: str, timeout: float = 15) -> list[ModelInfo]:
    resp = httpx.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
    resp.raise_for_status()
    return parse_groq_models(resp.json())


class CachedCatalog:
    """Caches a model list for `ttl_seconds`.

    The fetch function is passed on every call (not stored), so a user's key used for
    fetching is never kept alive inside the shared cache.
    If a refresh fails but an older list exists, the older list is returned.
    """

    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._clock = clock
        self._models: list[ModelInfo] | None = None
        self._fetched_at = 0.0
        self._lock = threading.Lock()

    def get(
        self, fetch: Callable[[], list[ModelInfo]], force_refresh: bool = False
    ) -> list[ModelInfo]:
        with self._lock:
            fresh = self._models is not None and self._clock() - self._fetched_at < self._ttl
            if fresh and not force_refresh:
                return list(self._models or [])
            try:
                self._models = fetch()
                self._fetched_at = self._clock()
            except Exception:
                if self._models is None:
                    raise
                # stale-but-usable beats nothing
            return list(self._models)
