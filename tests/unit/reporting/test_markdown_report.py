from __future__ import annotations

from archoptimize.calculators.design_metrics import measure_design
from archoptimize.reporting.markdown_report import build_report, findings_section
from archoptimize.schemas import Finding, Pillar, PillarScore, ReviewResult, Severity, Verdict
from archoptimize.schemas.candidate_design import CandidateDesign, DesignChange
from archoptimize.schemas.design_patch import ComponentUpdate, DesignPatch, apply_design_patch
from archoptimize.schemas.doc_chunk import DocChunk
from evaluation.eval_cases import load_cases

SUB = load_cases(only="01_single")[0].submission
REVISED = apply_design_patch(
    SUB.design,
    DesignPatch(update_components=[ComponentUpdate(id="orders-db", availability_zones=2)]),
)
CHUNK = DocChunk(
    chunk_id="rel-0001",
    pillar=Pillar.RELIABILITY,
    doc_title="Rel",
    page=3,
    url="https://x#page=3",
    text="t",
)
FINDING = Finding(
    id="REL-1",
    pillar=Pillar.RELIABILITY,
    severity=Severity.HIGH,
    title="Single-AZ DB | risky",
    component_ids=["orders-db"],
    evidence="1 AZ",
    recommendation="Multi-AZ",
    citation_chunk_ids=["rel-0001"],
)


def result(**extra) -> ReviewResult:
    return ReviewResult(
        verdict=Verdict.APPROVE_WITH_CHANGES,
        summary="Needs Multi-AZ.",
        findings=[FINDING],
        pillar_scores=[PillarScore(pillar=Pillar.RELIABILITY, score=2, rationale="SPOF | db")],
        sources=[CHUNK],
        original_metrics=measure_design(SUB.design, SUB.requirements),
        models_used={"Chair": "groq:openai/gpt-oss-120b"},
        **extra,
    )


def test_full_report_with_redesign():
    revised_metrics = measure_design(REVISED, SUB.requirements)
    report = build_report(
        SUB,
        result(
            revised_design=REVISED,
            revised_metrics=revised_metrics,
            design_changes=[DesignChange(description="Enable Multi-AZ", finding_ids=["REL-1"])],
            candidates=[
                CandidateDesign(
                    name="Multi-AZ",
                    approach="a",
                    design=REVISED,
                    changes=[],
                    trade_offs="t",
                    metrics=revised_metrics,
                    critic_score=8,
                )
            ],
            critic_rationale="Cheapest fix.",
            redesign_rounds=1,
        ),
    )
    assert "AI suggestion, not an approval" in report
    assert "🟡 Approve with changes" in report
    assert "[rel-0001](https://x#page=3)" in report  # citation links to the source page
    assert "class n_orders_db changed" in report  # after-diagram highlight
    assert "~ orders-db.availability_zones: 1 → 2" in report
    assert "_(fixes REL-1)_" in report and "critic 8/10" in report
    assert "SPOF \\| db" in report  # table-safe escaping


def test_no_findings_and_uncited_marker():
    assert "No findings" in findings_section(ReviewResult(verdict=Verdict.APPROVE))
    text = findings_section(result(uncited_finding_ids=["REL-1"]))
    assert "_uncited_" in text
