from __future__ import annotations

import pytest

from archoptimize.schemas import Finding, Pillar, ReviewResult, Severity, Verdict
from evaluation.eval_cases import load_cases
from evaluation.scoring import score_case, summarize


def finding(id, pillar, components, severity=Severity.HIGH) -> Finding:
    return Finding(
        id=id,
        pillar=pillar,
        severity=severity,
        title="t",
        component_ids=components,
        evidence="e",
        recommendation="r",
    )


@pytest.fixture(scope="module")
def monolith():
    return load_cases(only="01_single_az_monolith")[0]


def test_perfect_review(monolith):
    result = ReviewResult(
        verdict=Verdict.APPROVE_WITH_CHANGES,
        findings=[
            finding("R1", Pillar.RELIABILITY, ["orders-db"]),
            finding("R2", Pillar.RELIABILITY, ["web"]),
        ],
    )
    score = score_case(monolith, result, 1.0)
    assert (score.flaws_found, score.flaws_planted) == (2, 2)
    assert score.verdict_correct and score.false_alarms == 0 and score.missed_flaws == []


def test_wrong_pillar_or_component_does_not_match(monolith):
    result = ReviewResult(
        verdict=Verdict.APPROVE,
        findings=[
            finding("X1", Pillar.COST_OPTIMIZATION, ["orders-db"]),  # wrong pillar
            finding("X2", Pillar.RELIABILITY, ["users"]),  # wrong component
        ],
    )
    score = score_case(monolith, result, 0.0)
    assert score.flaws_found == 0
    assert score.false_alarms == 2  # both HIGH and unexplained
    assert not score.verdict_correct


def test_one_finding_cannot_count_for_two_flaws(monolith):
    both = finding("R1", Pillar.RELIABILITY, ["orders-db", "web"])
    score = score_case(monolith, ReviewResult(verdict=Verdict.REJECT, findings=[both]), 0.0)
    assert score.flaws_found == 1


def test_secondary_issues_and_low_severity_extras_are_not_false_alarms(monolith):
    result = ReviewResult(
        verdict=Verdict.REJECT,
        findings=[
            finding("S1", Pillar.SECURITY, ["web"]),  # known secondary issue (no WAF)
            finding("L1", Pillar.COST_OPTIMIZATION, ["web"], Severity.LOW),  # minor extra
        ],
    )
    score = score_case(monolith, result, 0.0)
    assert score.false_alarms == 0
    assert score.unmatched_findings == 1


def test_duplicate_finding_ids_are_handled(monolith):
    result = ReviewResult(
        verdict=Verdict.REJECT,
        findings=[
            finding("F", Pillar.RELIABILITY, ["orders-db"]),
            finding("F", Pillar.RELIABILITY, ["web"]),
        ],
    )
    assert score_case(monolith, result, 0.0).flaws_found == 2


def test_behaviour_checks():
    case = load_cases(only="05_prompt_injection")[0]
    flagged = ReviewResult(verdict=Verdict.REJECT, input_flagged=True)
    assert score_case(case, flagged, 0.0).behaviours == {"input_flagged": True}
    assert score_case(case, ReviewResult(verdict=Verdict.REJECT), 0.0).behaviours == {
        "input_flagged": False
    }


def test_crashed_review_counts_as_missed(monolith):
    score = score_case(monolith, None, 0.5, error="RuntimeError: boom")
    assert score.flaws_found == 0 and not score.verdict_correct and score.error


def test_summary_math(monolith):
    good = score_case(
        monolith,
        ReviewResult(
            verdict=Verdict.REJECT,
            findings=[finding("R1", Pillar.RELIABILITY, ["orders-db"])],
            tokens_used=1000,
        ),
        2.0,
    )
    bad = score_case(monolith, None, 4.0, error="boom")
    summary = summarize("test", [good, bad])
    assert summary.flaw_recall == 0.25  # 1 of 4 planted flaws
    assert summary.verdict_accuracy == 0.5
    assert summary.avg_latency_seconds == 3.0
    assert summary.avg_tokens == 1000
    assert summary.errors == 1
