"""One real baseline review (uses Groq). Run with: uv run python -m pytest -m live"""

from __future__ import annotations

import pytest

from archoptimize.agents.baseline_reviewer import review_baseline
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.schemas import Verdict
from evaluation.eval_cases import load_cases

pytestmark = pytest.mark.live


def test_baseline_reviews_the_monolith():
    keys = ProviderKeys.from_env()
    if keys.groq is None:
        pytest.skip("GROQ_API_KEY not set")
    case = load_cases(only="01_single_az_monolith")[0]
    result = review_baseline(case.submission, keys=keys)
    assert result.verdict is not Verdict.APPROVE
    assert result.findings
    assert result.tokens_used
