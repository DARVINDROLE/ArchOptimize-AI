from __future__ import annotations

from archoptimize.agents.chair_agent import apply_chair_decisions
from archoptimize.agents.reviewer_selector import select_pillars
from archoptimize.schemas import ChairDraft, Finding, Pillar, Severity, SeverityAdjustment, Verdict
from evaluation.eval_cases import load_cases


def finding(id, severity=Severity.HIGH):
    return Finding(
        id=id,
        pillar=Pillar.SECURITY,
        severity=severity,
        title="t",
        evidence="e",
        recommendation="r",
    )


def chair(duplicates=(), adjustments=()):
    return ChairDraft(
        summary="s",
        duplicate_finding_ids=list(duplicates),
        severity_adjustments=list(adjustments),
        requirement_conflicts=[],
        assumptions=[],
        verdict=Verdict.APPROVE,
    )


def test_duplicates_removed_severities_adjusted_and_sorted():
    findings = [finding("A", Severity.MEDIUM), finding("B"), finding("C", Severity.LOW)]
    draft = chair(
        duplicates=["B"],
        adjustments=[SeverityAdjustment(finding_id="C", severity=Severity.CRITICAL, reason="r")],
    )
    result = apply_chair_decisions(findings, draft)
    assert [(f.id, f.severity) for f in result] == [
        ("C", Severity.CRITICAL),
        ("A", Severity.MEDIUM),
    ]


def test_chair_cannot_delete_every_finding():
    assert len(apply_chair_decisions([finding("A")], chair(duplicates=["A"]))) == 1


def test_unknown_ids_in_chair_output_are_ignored():
    result = apply_chair_decisions([finding("A")], chair(duplicates=["ZZZ"]))
    assert [f.id for f in result] == ["A"]


def test_pci_reviewer_only_when_required():
    assert Pillar.COMPLIANCE in select_pillars(load_cases(only="02_pci")[0].submission)
    assert select_pillars(load_cases(only="01_single")[0].submission) == [
        Pillar.SECURITY,
        Pillar.RELIABILITY,
        Pillar.COST_OPTIMIZATION,
        Pillar.PERFORMANCE_EFFICIENCY,
    ]
