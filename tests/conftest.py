"""Shared test fixtures.

Unit tests never use real keys or the network. Tests that call real APIs live in
tests/live/, are marked `@pytest.mark.live`, and only run with `pytest -m live`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from archoptimize.llm.model_catalog import ModelInfo, parse_openrouter_models

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeClock:
    """A clock we can move forward by hand, to test caches and cooldowns."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def fake_clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def openrouter_catalog_payload() -> dict:
    return json.loads((FIXTURES_DIR / "openrouter_models.json").read_text(encoding="utf-8"))


@pytest.fixture
def openrouter_models(openrouter_catalog_payload: dict) -> list[ModelInfo]:
    return parse_openrouter_models(openrouter_catalog_payload)
