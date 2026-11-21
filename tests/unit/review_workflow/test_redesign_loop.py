"""The Architect → Critic → re-review loop, end to end with fake LLMs."""

from __future__ import annotations

from archoptimize.review_workflow.workflow_runner import run_review
from archoptimize.schemas import (
    ChairDraft,
    Component,
    ComponentType,
    Finding,
    Pillar,
    PillarReviewDraft,
    Severity,
    Verdict,
)
from archoptimize.schemas.candidate_design import (
    ArchitectDraft,
    CandidateProposal,
    CandidateScore,
    CriticDraft,
    DesignChange,
)
from archoptimize.schemas.design_patch import ComponentUpdate, DesignPatch
from evaluation.eval_cases import load_cases
from tests.fake_llm import KEYS, fake_router

MONOLITH = load_cases(only="01_single")[0].submission


def single_az_finding() -> Finding:
    return Finding(
        id="X",
        pillar=Pillar.RELIABILITY,
        severity=Severity.HIGH,
        title="Single-AZ database",
        component_ids=["orders-db"],
        evidence="1 AZ",
        recommendation="Multi-AZ",
    )


def reviewer(messages):
    """Flags the single-AZ DB until the design spans 2 AZs."""
    design_text = messages[1][1]
    fixed = (
        '"id":"orders-db"' in design_text
        and '"availability_zones":2' in design_text.split('"id":"orders-db"')[1].split("}")[0]
    )
    return PillarReviewDraft(
        findings=[] if fixed else [single_az_finding()],
        score=5 if fixed else 2,
        score_rationale="r",
        assumptions=[],
    )


CHAIR = ChairDraft(
    summary="Single points of failure.",
    duplicate_finding_ids=[],
    severity_adjustments=[],
    requirement_conflicts=[],
    assumptions=[],
    verdict=Verdict.APPROVE_WITH_CHANGES,
)

ARCHITECT = ArchitectDraft(
    candidates=[
        CandidateProposal(
            name="Multi-AZ DB",
            approach="Enable Multi-AZ on the database.",
            patch=DesignPatch(
                update_components=[ComponentUpdate(id="orders-db", availability_zones=2)]
            ),
            changes=[DesignChange(description="Multi-AZ", finding_ids=["REL-1"])],
            trade_offs="Doubles DB cost.",
        ),
        CandidateProposal(
            name="Broken option",
            approach="Updates a component that does not exist.",
            patch=DesignPatch(update_components=[ComponentUpdate(id="ghost", replicas=2)]),
            changes=[],
            trade_offs="-",
        ),
        CandidateProposal(
            name="Add cache only",
            approach="Adds a cache; does not fix the DB.",
            patch=DesignPatch(
                add_components=[
                    Component(
                        id="cache",
                        name="Cache",
                        type=ComponentType.CACHE,
                        instance_type="cache.t3.medium",
                    )
                ],
                add_edges=[{"from": "web", "to": "cache"}],
            ),
            changes=[DesignChange(description="cache", finding_ids=[])],
            trade_offs="Cheap.",
        ),
    ]
)

CRITIC = CriticDraft(
    scores=[
        CandidateScore(
            candidate_name="Multi-AZ DB",
            meets_requirements=False,
            fixed_finding_ids=["REL-1"],
            score=8,
            strengths="s",
            weaknesses="w",
        ),
        CandidateScore(
            candidate_name="Add cache only",
            meets_requirements=False,
            fixed_finding_ids=[],
            score=3,
            strengths="s",
            weaknesses="w",
        ),
    ],
    winner_name="multi-az db",  # case differs on purpose
    rationale="Fixes the blocking finding.",
)


def responses(critic=CRITIC):
    return {
        "text": "0.0",
        PillarReviewDraft: reviewer,
        ChairDraft: CHAIR,
        ArchitectDraft: ARCHITECT,
        CriticDraft: critic,
    }


def test_redesign_loop_fixes_the_flaw_and_reports_everything():
    calls: list = []
    events: list[str] = []
    result = run_review(
        MONOLITH, keys=KEYS, router=fake_router(responses(), calls), on_event=events.append
    )

    assert result.revised_design is not None
    assert result.revised_design.component("orders-db").availability_zones == 2
    assert [c.name for c in result.candidates] == [
        "Multi-AZ DB",
        "Add cache only",
    ]  # broken dropped
    assert any("Broken option" in w for w in result.warnings)
    assert result.candidates[0].critic_score == 8
    assert result.critic_rationale == "Fixes the blocking finding."
    assert result.remaining_issues == []  # re-review found nothing blocking
    assert result.redesign_rounds == 1
    assert result.design_changes[0].finding_ids == ["REL-1"]
    # numbers come from the calculators: Multi-AZ doubles the DB cost and raises availability
    assert (
        result.revised_metrics.cost.total_monthly_usd
        > result.original_metrics.cost.total_monthly_usd
    )
    assert (
        result.revised_metrics.availability.estimated_percent
        > result.original_metrics.availability.estimated_percent
    )
    assert "Architect" in result.models_used and "Critic" in result.models_used
    assert events[-1] == "Review complete (with redesign)"
    assert sum(1 for name, _ in calls if name == "ArchitectDraft") == 1


def test_loop_stops_after_two_rounds_when_issues_remain():
    always_flag = dict(responses())
    always_flag[PillarReviewDraft] = PillarReviewDraft(
        findings=[single_az_finding()], score=2, score_rationale="r", assumptions=[]
    )
    calls: list = []
    result = run_review(MONOLITH, keys=KEYS, router=fake_router(always_flag, calls))
    assert result.redesign_rounds == 2
    assert result.remaining_issues  # reported, not hidden
    assert sum(1 for name, _ in calls if name == "ArchitectDraft") == 2


def test_critic_failure_falls_back_to_rule_based_pick():
    def broken(_messages):
        raise RuntimeError("critic down")

    result = run_review(MONOLITH, keys=KEYS, router=fake_router(responses(critic=broken)))
    assert result.revised_design is not None
    assert any("Critic failed" in w for w in result.warnings)


def test_approved_design_is_not_redesigned():
    approve = dict(responses())
    approve[ChairDraft] = CHAIR.model_copy(update={"verdict": Verdict.APPROVE})
    calls: list = []
    result = run_review(MONOLITH, keys=KEYS, router=fake_router(approve, calls))
    assert result.revised_design is None and result.original_metrics is not None
    assert not any(name == "ArchitectDraft" for name, _ in calls)
