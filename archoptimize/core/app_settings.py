"""App-wide limits. Defaults live here; later steps may let environment variables override them."""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel


class AppSettings(BaseModel):
    # Untrusted input is capped before anything else touches it.
    max_design_chars: int = 15_000


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    return AppSettings()
