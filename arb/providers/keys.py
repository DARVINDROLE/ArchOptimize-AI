"""API keys, held only in memory for one session (BYOK = bring your own key).

`SecretStr` hides the value in repr/str/logs: printing a ProviderKeys shows '**********'.
Locally, keys come from `.env`; in the deployed app the UI passes them per session.
"""

from __future__ import annotations

import os
import re

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, SecretStr

_PLACEHOLDER = "your_key_here"

# Shapes of real keys, used to scrub error messages before they are shown anywhere.
_KEY_PATTERN = re.compile(r"(gsk_[A-Za-z0-9]{8,}|sk-or-[A-Za-z0-9-]{8,}|sk-[A-Za-z0-9_-]{16,})")


def redact(text: str) -> str:
    """Replace anything that looks like an API key with a marker."""
    return _KEY_PATTERN.sub("[redacted-key]", text)


def _secret(value: str | None) -> SecretStr | None:
    if value is None:
        return None
    value = value.strip()
    if not value or _PLACEHOLDER in value:
        return None
    return SecretStr(value)


class ProviderKeys(BaseModel):
    model_config = ConfigDict(frozen=True)

    groq: SecretStr | None = None
    openrouter: SecretStr | None = None

    @classmethod
    def from_values(cls, groq: str | None = None, openrouter: str | None = None) -> ProviderKeys:
        return cls(groq=_secret(groq), openrouter=_secret(openrouter))

    @classmethod
    def from_env(cls) -> ProviderKeys:
        load_dotenv()  # no-op if there is no .env file
        return cls.from_values(os.getenv("GROQ_API_KEY"), os.getenv("OPENROUTER_API_KEY"))
