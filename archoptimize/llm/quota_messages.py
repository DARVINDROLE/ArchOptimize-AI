"""Turn provider quota errors into plain advice for the user.

Free tiers have per-minute limits (handled by retries/backoff) and per-DAY limits:
- Groq: tokens/requests per day, per model ("... on tokens per day (TPD) ...").
- OpenRouter: free-model requests per day, per account ("free-models-per-day").
A daily limit cannot be waited out in seconds, so the user needs to know which provider
is exhausted and what to do.
"""

from __future__ import annotations

import re

_MODEL = re.compile(r"model `([^`]+)`")


def _normalise(text: str) -> str:
    # OpenRouter writes "free-models-per-day"; Groq writes "tokens per day"
    return text.lower().replace("-", " ").replace("_", " ")


def is_daily_limit(text: str) -> bool:
    lowered = _normalise(text)
    return ("per day" in lowered or "daily lim" in lowered) and (
        "rate limit" in lowered or "429" in lowered
    )


def daily_limit_hint(text: str) -> str | None:
    if not is_daily_limit(text):
        return None
    lowered = _normalise(text)
    groq = "tokens per day" in lowered or "requests per day" in lowered
    openrouter = "free models per day" in lowered or "openrouter" in lowered
    parts: list[str] = []
    if groq or not openrouter:
        match = _MODEL.search(text)
        model = match.group(1) if match else "a model"
        parts.append(f"your **Groq** key reached its daily free-tier limit for `{model}`")
    if openrouter:
        parts.append(
            "your **OpenRouter** account reached its daily free-model request limit "
            "(OpenRouter raises it if the account ever adds credit)"
        )
    advice = (
        "Daily limits reset after ~24 h."
        if openrouter
        else "Daily limits reset after ~24 h; adding an OpenRouter key gives the app "
        "more free models to fall back on."
    )
    sentence = " and ".join(parts)
    return (
        "⚠️ " + sentence[0].upper() + sentence[1:] + ". The review used other models where "
        "it could, but some steps may be missing. " + advice
    )
