"""A configurable fake chat model for agent/workflow tests (no network, no keys).

`responses` maps a schema class (for structured calls) or the string "text" (plain calls)
to either a value or a function(messages) -> value.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_catalog import ModelInfo
from archoptimize.llm.model_router import ModelRouter
from archoptimize.llm.role_config import load_settings

KEYS = ProviderKeys.from_values("gsk_" + "x" * 40, None)


class _Msg:
    def __init__(self, content: str):
        self.content = content
        self.usage_metadata = {"total_tokens": 100}


class FakeChat:
    def __init__(self, responses: dict, calls: list):
        self.responses, self.calls = responses, calls

    def _value(self, key: Any, messages: Any) -> Any:
        value = self.responses[key]
        return value(messages) if callable(value) and not isinstance(value, type) else value

    def invoke(self, messages, **_kw):
        self.calls.append(("text", messages))
        return _Msg(str(self._value("text", messages)))

    def with_structured_output(self, schema, method, include_raw=False):
        chat = self

        class _Bound:
            def invoke(self, messages, **_kw):
                chat.calls.append((schema.__name__, messages))
                parsed = chat._value(schema, messages)
                return {"raw": _Msg(""), "parsed": parsed, "parsing_error": None}

        return _Bound()


def fake_router(responses: dict[Any, Any | Callable], calls: list | None = None) -> ModelRouter:
    calls = calls if calls is not None else []
    return ModelRouter(
        load_settings(),
        chat_factory=lambda _c, _k: FakeChat(responses, calls),
        openrouter_fetch=lambda: [],
        # a live non-OpenAI Groq model, so the Critic has a different-family fallback
        groq_fetch=lambda _k: [ModelInfo(id="qwen/qwen3-32b", context_length=131_072)],
    )
