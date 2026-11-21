"""Load `arb/config/models.yaml` into typed settings.

Keeping model IDs in YAML (not code) means we can swap models without touching agents.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "models.yaml"

Provider = Literal["groq", "openrouter"]


class RoleRequirements(BaseModel):
    """What a model must support to serve a role (used to filter OpenRouter's catalog)."""

    image_input: bool = False
    structured_output: bool = True
    tools: bool = False
    min_context: int = 0
    different_family_from: str | None = None  # name of another role


class RoleConfig(BaseModel):
    provider: Provider
    models: list[str] = Field(default_factory=list)  # Groq model IDs, in try order
    requirements: RoleRequirements = Field(default_factory=RoleRequirements)
    allow_fallback: bool = True  # Groq roles: may fall back to OpenRouter
    groq_fallback: bool = False  # OpenRouter roles: may fall back to a live Groq model

    @model_validator(mode="after")
    def _groq_roles_need_models(self) -> RoleConfig:
        if self.provider == "groq" and not self.models:
            raise ValueError("a groq role needs at least one model id")
        return self


class GroqSettings(BaseModel):
    models_url: str = "https://api.groq.com/openai/v1/models"
    max_retries: int = 2
    timeout_seconds: float = 60
    cooldown_seconds: int = 60
    structured_method: str = "json_schema"
    live_fallback_limit: int = 2
    # Live Groq models whose id contains one of these are not chat models.
    non_chat_patterns: list[str] = Field(
        default_factory=lambda: ["whisper", "guard", "tts", "orpheus", "playai", "compound"]
    )


class OpenRouterSettings(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"
    catalog_url: str = "https://openrouter.ai/api/v1/models"
    catalog_ttl_seconds: int = 3600
    max_attempts: int = 3
    max_retries: int = 1
    timeout_seconds: float = 90
    cooldown_seconds: int = 300
    fallback_min_context: int = 32000
    prefer: list[str] = Field(default_factory=list)
    app_title: str = "ArchOptimize AI"


class ModelSettings(BaseModel):
    groq: GroqSettings = Field(default_factory=GroqSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    roles: dict[str, RoleConfig]

    @model_validator(mode="after")
    def _family_refs_exist(self) -> ModelSettings:
        for name, role in self.roles.items():
            ref = role.requirements.different_family_from
            if ref is not None and ref not in self.roles:
                raise ValueError(f"role '{name}' refers to unknown role '{ref}'")
        return self

    def role(self, name: str) -> RoleConfig:
        try:
            return self.roles[name]
        except KeyError:
            known = ", ".join(sorted(self.roles))
            raise ValueError(f"unknown role '{name}' (known: {known})") from None


def load_settings(path: Path | str = DEFAULT_CONFIG_PATH) -> ModelSettings:
    with open(path, encoding="utf-8") as f:
        return ModelSettings.model_validate(yaml.safe_load(f))


@lru_cache(maxsize=1)
def default_settings() -> ModelSettings:
    return load_settings()
