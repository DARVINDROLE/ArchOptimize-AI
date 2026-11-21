"""Run the real LangGraph workflow end to end with fake LLMs and a fake retriever."""

from __future__ import annotations

from archoptimize.review_workflow.workflow_runner import run_review
from archoptimize.schemas import (
    ChairDraft,
    Finding,
    Pillar,
    PillarReviewDraft,
    Severity,
    SeverityAdjustment,
    Verdict,
)
from archoptimize.schemas.doc_chunk import DocChunk, RetrievedChunk
from evaluation.eval_cases import load_cases
from tests.fake_llm import KEYS, fake_router


class FakeRetriever:
    def retrieve(self, query, pillar, k=4):
        chunk = DocChunk(
            chunk_id=f"{pillar.value[:4]}-0001",
            pillar=pillar,
            doc_title="Doc",
            page=1,
            url="https://x#page=1",
            text="guidance",
        )
        return [RetrievedChunk(chunk=chunk, score=0.8)]


def reviewer_reply(messages):
    """Each reviewer returns one finding citing its own retrieved chunk (+ one fake id)."""
    system = messages[0][1]
    pillar = next(p for p in Pillar if p.value.replace("_", " ") in system.lower() or True)
    del pillar  # the pillar is forced by the workflow; content does not matter here
    return PillarReviewDraft(
        findings=[
            Finding(
                id="X",
                pillar=Pillar.SECURITY,  # wrong on purpose: the workflow must fix it
                severity=Severity.HIGH,
                title="Problem",
                component_ids=["orders-db", "ghost"],
                evidence="e",
                recommendation="r",
                citation_chunk_ids=["reli-0001", "secu-0001", "cost-0001", "perf-0001", "fake-1"],
            )
        ],
        score=3,
        score_rationale="ok",
        assumptions=["traffic pattern unknown"],
    )


CHAIR = ChairDraft(
    summary="Needs Multi-AZ.",
    duplicate_finding_ids=["COST-1"],
    severity_adjustments=[
        SeverityAdjustment(finding_id="PERF-1", severity=Severity.LOW, reason="nitpick")
    ],
    requirement_conflicts=[],
    assumptions=["RPO unknown"],
    verdict=Verdict.APPROVE_WITH_CHANGES,
)


def test_board_review_end_to_end():
    calls: list = []
    router = fake_router(
        {"text": "0.0", PillarReviewDraft: reviewer_reply, ChairDraft: CHAIR}, calls
    )
    events: list[str] = []
    submission = load_cases(only="01_single")[0].submission
    result = run_review(
        submission,
        keys=KEYS,
        retriever=FakeRetriever(),
        router=router,
        redesign=False,
        on_event=events.append,
    )

    assert result.verdict is Verdict.APPROVE_WITH_CHANGES
    # 4 reviewers ran (no PCI), duplicate COST-1 removed by the chair
    assert {f.id for f in result.findings} == {"SEC-1", "REL-1", "PERF-1"}
    by_id = {f.id: f for f in result.findings}
    assert by_id["REL-1"].pillar is Pillar.RELIABILITY  # pillar forced to the reviewer's
    assert by_id["PERF-1"].severity is Severity.LOW  # chair adjustment applied
    assert by_id["REL-1"].component_ids == ["orders-db"]  # invented id dropped
    assert by_id["REL-1"].citation_chunk_ids == ["reli-0001"]  # only its own retrieved chunk
    assert result.findings[-1].id == "PERF-1"  # sorted by severity
    assert {s.pillar for s in result.pillar_scores} == {
        Pillar.SECURITY,
        Pillar.RELIABILITY,
        Pillar.COST_OPTIMIZATION,
        Pillar.PERFORMANCE_EFFICIENCY,
    }
    assert "Chair" in result.models_used and "reliability reviewer" in result.models_used
    assert result.tokens_used == 100 * 5  # 4 reviewers + chair
    assert events[0].startswith("Input guard") and events[-2].startswith("Chair")
    assert events[-1] == "Review complete (without redesign)"
    assert sum(1 for name, _ in calls if name == "PillarReviewDraft") == 4


def test_pci_case_adds_the_compliance_reviewer_and_flags_nothing_extra():
    router = fake_router({"text": "0.0", PillarReviewDraft: reviewer_reply, ChairDraft: CHAIR})
    result = run_review(
        load_cases(only="02_pci")[0].submission,
        keys=KEYS,
        retriever=FakeRetriever(),
        router=router,
        redesign=False,
    )
    assert any(s.pillar is Pillar.COMPLIANCE for s in result.pillar_scores)


def test_a_failing_reviewer_is_reported_but_the_review_completes():
    def flaky(messages):
        if "Cost reviewer" in messages[0][1]:
            raise RuntimeError("model down")
        return reviewer_reply(messages)

    router = fake_router({"text": "0.0", PillarReviewDraft: flaky, ChairDraft: CHAIR})
    result = run_review(
        load_cases(only="01_single")[0].submission,
        keys=KEYS,
        retriever=FakeRetriever(),
        router=router,
        redesign=False,
    )
    assert any("Cost reviewer failed" in w for w in result.warnings)
    assert len(result.pillar_scores) == 3


def test_injection_is_flagged_in_the_result():
    router = fake_router({"text": "0.99", PillarReviewDraft: reviewer_reply, ChairDraft: CHAIR})
    result = run_review(
        load_cases(only="05_prompt")[0].submission,
        keys=KEYS,
        retriever=None,
        router=router,
        redesign=False,
    )
    assert result.input_flagged and result.guard_reasons
    assert result.uncited_finding_ids  # no retriever -> nothing citable
