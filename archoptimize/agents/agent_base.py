"""Shared plumbing for agents: load a prompt file, call the role's LLM, get a typed result.

Every agent follows the same pattern:
    system prompt (from agents/prompts/<agent>.md)  +  user message (the data)
    → get_llm(role).with_structured_output(Schema)  → a validated Pydantic object
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter, get_router

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Read agents/prompts/<name>.md."""
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def render_prompt(template: str, **values: str) -> str:
    """Fill `{name}` placeholders. Unknown or missing names raise, so typos are caught early.
    (We don't use str.format: prompts may contain JSON braces.)"""
    needed = set(_PLACEHOLDER.findall(template))
    missing = needed - values.keys()
    if missing:
        raise KeyError(f"prompt placeholders without a value: {sorted(missing)}")
    unused = values.keys() - needed
    if unused:
        raise KeyError(f"values for placeholders not in the prompt: {sorted(unused)}")
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], template)


@dataclass(frozen=True)
class AgentCall[T: BaseModel]:
    output: T
    model: str  # e.g. "groq:openai/gpt-oss-120b" (shown in the UI as "model used")
    tokens: int | None


def call_structured[T: BaseModel](
    role: str,
    schema: type[T],
    system_prompt: str,
    user_message: str,
    *,
    keys: ProviderKeys | None = None,
    router: ModelRouter | None = None,
) -> AgentCall[T]:
    router = router or get_router()
    llm = router.get_llm(role, keys or ProviderKeys.from_env()).with_structured_output(schema)
    output = llm.invoke([("system", system_prompt), ("human", user_message)])
    assert llm.last_candidate is not None
    return AgentCall(output=output, model=llm.last_candidate.label, tokens=llm.last_tokens)
