"""`get_llm(role)`: the ONLY way agents get an LLM.

How a call is routed:
1. Build an ordered list of candidate models for the role:
   - Groq role:       its Groq models from models.yaml (e.g. 120b -> 20b),
                      then (fallback) up to N free OpenRouter models that fit the role.
   - OpenRouter role: up to N free OpenRouter models picked from the live catalog,
                      then (critic only) a different-family live Groq model.
2. Try them in order. A model that fails is put on cooldown and the next is tried.
   An auth error (bad key) skips the rest of that provider.
3. If all fail, raise AllModelsFailedError with a key-free summary.

Agents use it like a normal LangChain chat model:
    llm = get_llm("reviewer", keys)
    findings = llm.with_structured_output(FindingList).invoke(messages)
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from arb.providers.config import ModelSettings, RoleConfig, RoleRequirements, default_settings
from arb.providers.cooldown import Cooldown
from arb.providers.groq_client import make_groq_chat
from arb.providers.keys import ProviderKeys, redact
from arb.providers.model_catalog import (
    CachedCatalog,
    ModelInfo,
    family_of,
    fetch_groq_models,
    fetch_openrouter_models,
)
from arb.providers.openrouter_client import make_openrouter_chat
from arb.providers.selector import select_models

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Candidate:
    provider: Literal["groq", "openrouter"]
    model: str
    structured_method: str = "json_schema"

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


class NoModelAvailableError(RuntimeError):
    pass


class AllModelsFailedError(RuntimeError):
    def __init__(self, role: str, attempts: list[tuple[str, str]]):
        self.role = role
        self.attempts = attempts
        lines = "\n".join(f"  - {model}: {err}" for model, err in attempts)
        super().__init__(f"All models failed for role '{role}':\n{lines}")


def _is_auth_error(exc: Exception) -> bool:
    # 401 = bad key; 403 = key not allowed (e.g. OpenRouter privacy settings block free models)
    return getattr(exc, "status_code", None) in (401, 403)


def _describe(exc: Exception) -> str:
    return redact(f"{type(exc).__name__}: {str(exc)[:200]}")


ChatFactory = Callable[[Candidate, ProviderKeys], Any]


class RoutedLLM:
    """A chat model that tries several candidate models in order."""

    def __init__(
        self,
        role: str,
        candidates: list[Candidate],
        make_chat: Callable[[Candidate], Any],
        on_failure: Callable[[Candidate], None],
    ):
        self.role = role
        self.candidates = candidates
        self._make_chat = make_chat
        self._on_failure = on_failure
        self.last_candidate: Candidate | None = None  # which model answered (shown in the UI)

    # -- public API (mirrors the LangChain methods agents need) --
    def invoke(self, input: Any, **kwargs: Any) -> Any:
        return self._run(lambda chat, _c: chat.invoke(input, **kwargs))

    async def ainvoke(self, input: Any, **kwargs: Any) -> Any:
        return await self._arun(lambda chat, _c: chat.ainvoke(input, **kwargs))

    def with_structured_output(self, schema: type) -> StructuredRoutedLLM:
        return StructuredRoutedLLM(self, schema)

    # -- the try-next loop --
    def _check_candidates(self) -> None:
        if not self.candidates:
            raise NoModelAvailableError(
                f"No model available for role '{self.role}'. "
                "Check that the needed API key is set (Groq required; OpenRouter for vision)."
            )

    def _record(self, c: Candidate, exc: Exception, attempts: list, dead: set) -> None:
        attempts.append((c.label, _describe(exc)))
        log.warning("role=%s model=%s failed: %s", self.role, c.label, attempts[-1][1])
        if _is_auth_error(exc):
            dead.add(c.provider)
        else:
            self._on_failure(c)

    def _run(self, call: Callable[[Any, Candidate], Any]) -> Any:
        self._check_candidates()
        attempts: list[tuple[str, str]] = []
        dead: set[str] = set()
        for c in self.candidates:
            if c.provider in dead:
                continue
            try:
                result = call(self._make_chat(c), c)
            except Exception as exc:
                self._record(c, exc, attempts, dead)
                continue
            self.last_candidate = c
            return result
        raise AllModelsFailedError(self.role, attempts)

    async def _arun(self, call: Callable[[Any, Candidate], Awaitable[Any]]) -> Any:
        self._check_candidates()
        attempts: list[tuple[str, str]] = []
        dead: set[str] = set()
        for c in self.candidates:
            if c.provider in dead:
                continue
            try:
                result = await call(self._make_chat(c), c)
            except Exception as exc:
                self._record(c, exc, attempts, dead)
                continue
            self.last_candidate = c
            return result
        raise AllModelsFailedError(self.role, attempts)


class StructuredRoutedLLM:
    """Same try-next loop, but every reply is parsed into `schema` (a Pydantic model).
    Invalid JSON counts as a failure, so the next model gets a chance."""

    def __init__(self, parent: RoutedLLM, schema: type):
        self._parent = parent
        self._schema = schema

    @property
    def last_candidate(self) -> Candidate | None:
        return self._parent.last_candidate

    def _bind(self, chat: Any, c: Candidate) -> Any:
        return chat.with_structured_output(self._schema, method=c.structured_method)

    def invoke(self, input: Any, **kwargs: Any) -> Any:
        return self._parent._run(lambda chat, c: self._bind(chat, c).invoke(input, **kwargs))

    async def ainvoke(self, input: Any, **kwargs: Any) -> Any:
        return await self._parent._arun(
            lambda chat, c: self._bind(chat, c).ainvoke(input, **kwargs)
        )


class ModelRouter:
    """Holds shared, key-free state: settings, catalog caches, cooldowns."""

    def __init__(
        self,
        settings: ModelSettings,
        *,
        chat_factory: ChatFactory | None = None,
        openrouter_fetch: Callable[[], list[ModelInfo]] | None = None,
        groq_fetch: Callable[[str], list[ModelInfo]] | None = None,
    ):
        self.settings = settings
        self._chat_factory = chat_factory or self._default_chat_factory
        self._openrouter_fetch = openrouter_fetch or (
            lambda: fetch_openrouter_models(settings.openrouter.catalog_url)
        )
        self._groq_fetch = groq_fetch or (
            lambda key: fetch_groq_models(settings.groq.models_url, key)
        )
        self._or_catalog = CachedCatalog(settings.openrouter.catalog_ttl_seconds)
        self._groq_catalog = CachedCatalog(settings.openrouter.catalog_ttl_seconds)
        self._cooldowns = {
            "groq": Cooldown(settings.groq.cooldown_seconds),
            "openrouter": Cooldown(settings.openrouter.cooldown_seconds),
        }

    # -- public --
    def get_llm(
        self,
        role: str,
        keys: ProviderKeys,
        *,
        only_provider: Literal["groq", "openrouter"] | None = None,
    ) -> RoutedLLM:
        candidates = self.candidates_for(role, keys, only_provider=only_provider)
        return RoutedLLM(
            role,
            candidates,
            make_chat=lambda c: self._chat_factory(c, keys),
            on_failure=lambda c: self._cooldowns[c.provider].mark(c.model),
        )

    def candidates_for(
        self,
        role: str,
        keys: ProviderKeys,
        *,
        only_provider: Literal["groq", "openrouter"] | None = None,
    ) -> list[Candidate]:
        rc = self.settings.role(role)
        use_groq = only_provider in (None, "groq") and keys.groq is not None
        use_or = only_provider in (None, "openrouter") and keys.openrouter is not None
        exclude = self._excluded_families(rc)
        out: list[Candidate] = []

        if rc.provider == "groq":
            if use_groq:
                out += [
                    Candidate("groq", m, self.settings.groq.structured_method)
                    for m in rc.models
                    if not self._cooldowns["groq"].is_cooling(m)
                ]
            if use_or and (rc.allow_fallback or only_provider == "openrouter"):
                req = rc.requirements.model_copy(
                    update={
                        "min_context": max(
                            rc.requirements.min_context,
                            self.settings.openrouter.fallback_min_context,
                        )
                    }
                )
                out += self._openrouter_candidates(req, exclude)
        else:
            if use_or:
                out += self._openrouter_candidates(rc.requirements, exclude)
            if use_groq and rc.groq_fallback and keys.groq is not None:
                out += self._groq_live_candidates(keys.groq.get_secret_value(), exclude)
        return out

    def openrouter_models(self) -> list[ModelInfo]:
        return self._or_catalog.get(self._openrouter_fetch)

    # -- helpers --
    def _excluded_families(self, rc: RoleConfig) -> set[str]:
        ref = rc.requirements.different_family_from
        if ref is None:
            return set()
        return {family_of(m) for m in self.settings.role(ref).models}

    def _openrouter_candidates(self, req: RoleRequirements, exclude: set[str]) -> list[Candidate]:
        try:
            models = self.openrouter_models()
        except Exception as exc:  # catalog down -> just no OpenRouter candidates
            log.warning("OpenRouter catalog unavailable: %s", _describe(exc))
            return []
        chosen = select_models(
            models,
            req,
            exclude_families=exclude,
            prefer=self.settings.openrouter.prefer,
            is_cooling=self._cooldowns["openrouter"].is_cooling,
            limit=self.settings.openrouter.max_attempts,
        )
        return [Candidate("openrouter", m.id, "json_schema") for m in chosen]

    def _groq_live_candidates(self, api_key: str, exclude: set[str]) -> list[Candidate]:
        try:
            models = self._groq_catalog.get(lambda: self._groq_fetch(api_key))
        except Exception as exc:
            log.warning("Groq model list unavailable: %s", _describe(exc))
            return []
        patterns = [p.lower() for p in self.settings.groq.non_chat_patterns]
        usable = [
            m
            for m in models
            if m.family not in exclude
            and not any(p in m.id.lower() for p in patterns)
            and not self._cooldowns["groq"].is_cooling(m.id)
        ]
        usable.sort(key=lambda m: (-m.context_length, m.id))
        # function_calling works on more Groq models than json_schema does
        return [
            Candidate("groq", m.id, "function_calling")
            for m in usable[: self.settings.groq.live_fallback_limit]
        ]

    def _default_chat_factory(self, c: Candidate, keys: ProviderKeys) -> Any:
        if c.provider == "groq":
            assert keys.groq is not None
            return make_groq_chat(c.model, keys.groq, self.settings.groq)
        assert keys.openrouter is not None
        return make_openrouter_chat(c.model, keys.openrouter, self.settings.openrouter)


_default_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    global _default_router
    if _default_router is None:
        _default_router = ModelRouter(default_settings())
    return _default_router


def get_llm(
    role: str,
    keys: ProviderKeys | None = None,
    *,
    only_provider: Literal["groq", "openrouter"] | None = None,
) -> RoutedLLM:
    """Get the LLM for a role. `keys` = this session's keys (default: from .env, for local dev)."""
    return get_router().get_llm(role, keys or ProviderKeys.from_env(), only_provider=only_provider)
