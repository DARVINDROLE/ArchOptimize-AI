"""Daily free-tier limits (found in the Step 6/7 eval): the review must still finish, and the
user must be told plainly what happened."""

from __future__ import annotations

from archoptimize.llm.quota_messages import daily_limit_hint
from archoptimize.review_workflow.workflow_nodes import fallback_chair_draft
from archoptimize.review_workflow.workflow_runner import run_review
from archoptimize.schemas import ChairDraft, Finding, Pillar, PillarReviewDraft, Severity, Verdict
from evaluation.eval_cases import load_cases
from tests.fake_llm import KEYS, fake_router

TPD_ERROR = (
    "Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b` in organization "
    "`org_x` service tier `on_demand` on tokens per day (TPD): Limit 200000, Used 199990"
)


def finding(severity: Severity) -> Finding:
    return Finding(
        id="X", pillar=Pillar.RELIABILITY, severity=severity, title="t", evidence="e",
        recommendation="r", component_ids=["orders-db"],
    )  # fmt: skip


def test_daily_limit_hint_names_the_model():
    hint = daily_limit_hint(TPD_ERROR)
    assert hint and "openai/gpt-oss-120b" in hint and "daily" in hint
    assert daily_limit_hint("429 Too Many Requests: tokens per minute") is None
    assert daily_limit_hint("some other error") is None


# Real shapes seen live on 2026-11-22: Groq's long JSON error, then OpenRouter's daily cap.
OPENROUTER_DAILY = (
    "openrouter:liquid/lfm-3-1.7b:free: OpenAIRateLimitError: Error code: 429 - Rate limit "
    "exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day"
)
ALL_FAILED = (
    "All models failed for role 'architect':\n"
    f"  - groq:openai/gpt-oss-120b: RateLimitError: {'x' * 250} {TPD_ERROR}\n"
    f"  - {OPENROUTER_DAILY}"
)


def test_openrouter_daily_limit_is_recognised():
    hint = daily_limit_hint(OPENROUTER_DAILY)
    assert hint and "OpenRouter" in hint and "adding an OpenRouter key" not in hint


def test_long_errors_keep_the_daily_limit_after_truncation():
    from archoptimize.review_workflow.workflow_nodes import _warning, redesign_note
    from archoptimize.schemas import ReviewResult

    warning = _warning(f"Architect failed: AllModelsFailedError: {ALL_FAILED}")
    assert len(warning) <= 300
    hint = daily_limit_hint(warning)
    assert hint and "Groq" in hint and "OpenRouter" in hint
    state = {"result": ReviewResult(verdict=Verdict.APPROVE), "redesign_round": 1,
             "warnings": [warning]}  # fmt: skip
    note = redesign_note(state, True)
    assert "both Groq and OpenRouter" in note and "few minutes" not in note


def test_other_errors_are_just_shortened():
    from archoptimize.review_workflow.workflow_nodes import _warning

    assert _warning("Critic failed: " + "y" * 500) == ("Critic failed: " + "y" * 500)[:300]


def test_fallback_verdict_follows_severities():
    assert fallback_chair_draft([finding(Severity.CRITICAL)], False).verdict is Verdict.REJECT
    assert (
        fallback_chair_draft([finding(Severity.MEDIUM)], False).verdict
        is Verdict.APPROVE_WITH_CHANGES
    )
    assert fallback_chair_draft([finding(Severity.LOW)], False).verdict is Verdict.APPROVE
    assert fallback_chair_draft([], True).verdict is Verdict.APPROVE_WITH_CHANGES  # flagged


def test_review_finishes_when_the_chair_hits_its_daily_limit():
    def chair_down(_messages):
        raise RuntimeError(TPD_ERROR)

    reviewer = PillarReviewDraft(
        findings=[finding(Severity.CRITICAL)], score=1, score_rationale="r", assumptions=[]
    )
    router = fake_router({"text": "0.0", PillarReviewDraft: reviewer, ChairDraft: chair_down})
    result = run_review(
        load_cases(only="01_")[0].submission, keys=KEYS, router=router, redesign=False
    )
    assert result.verdict is Verdict.REJECT
    assert result.models_used["Chair"] == "rule-based fallback"
    assert any("Chair failed" in w for w in result.warnings)
    assert any(daily_limit_hint(w) for w in result.warnings)
