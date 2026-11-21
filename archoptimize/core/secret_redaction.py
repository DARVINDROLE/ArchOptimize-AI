"""Scrub API keys out of any text before it is logged, traced or shown in the UI."""

from __future__ import annotations

import re

# Shapes of real keys: Groq (gsk_), OpenRouter (sk-or-), OpenAI-style (sk-), Hugging Face (hf_).
_KEY_PATTERN = re.compile(
    r"(gsk_[A-Za-z0-9]{8,}|sk-or-[A-Za-z0-9-]{8,}|sk-[A-Za-z0-9_-]{16,}|hf_[A-Za-z0-9]{16,})"
)

REDACTED = "[redacted-key]"


def redact(text: str) -> str:
    """Replace anything that looks like an API key with a marker."""
    return _KEY_PATTERN.sub(REDACTED, text)
