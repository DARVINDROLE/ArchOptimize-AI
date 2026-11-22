"""Turn provider quota errors into plain advice for the user.

Groq's free tier has per-minute limits (handled by retries/backoff) and per-DAY limits per
model (tokens per day / requests per day). A daily limit cannot be waited out in seconds,
so the user needs to know which model is exhausted and what to do.
"""

from __future__ import annotations

import re

_MODEL = re.compile(r"model `([^`]+)`")


def daily_limit_hint(text: str) -> str | None:
    lowered = text.lower()
    if "per day" not in lowered or ("rate limit" not in lowered and "429" not in lowered):
        return None
    match = _MODEL.search(text)
    model = match.group(1) if match else "a model"
    return (
        f"⚠️ Your Groq API key has reached its **daily** free-tier limit for `{model}`. "
        "The review used other models where it could, but some steps may be missing. "
        "Daily limits reset after ~24 h; adding an OpenRouter key gives the app more "
        "free models to fall back on."
    )
