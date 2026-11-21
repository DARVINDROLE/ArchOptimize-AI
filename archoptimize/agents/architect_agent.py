"""Architect: proposes three candidate redesigns in ONE call (Tree of Thoughts).

The LLM writes patches; code applies them to the original design, validates the result and
measures it with the calculators. Proposals whose patch does not fit are dropped (and
reported), never "fixed up" by guessing.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from archoptimize.agents.agent_base import call_structured, load_prompt
from archoptimize.calculators.design_metrics import measure_design
from archoptimize.core.untrusted_input import wrap_untrusted
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter
from archoptimize.schemas import ComponentGraph, DesignSubmission, Finding, Severity
from archoptimize.schemas.candidate_design import ArchitectDraft, CandidateDesign
from archoptimize.schemas.design_metrics import DesignMetrics
from archoptimize.schemas.design_patch import PatchError, apply_design_patch

ROLE = "architect"
COMPACT = {"separators": (",", ":")}
FIX_SEVERITIES = (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM)


@dataclass
class ArchitectResult:
    candidates: list[CandidateDesign]
    rejected: list[str]  # why proposals were dropped
    model: str
    tokens: int | None


def _finding_lines(findings: list[Finding]) -> str:
    rows = [
        {"id": f.id, "severity": f.severity.value, "title": f.title, "components": f.component_ids,
         "recommendation": f.recommendation}
        for f in findings
        if f.severity in FIX_SEVERITIES
    ]  # fmt: skip
    return json.dumps(rows, **COMPACT)


def build_user_message(
    submission: DesignSubmission,
    findings: list[Finding],
    metrics: DesignMetrics,
    open_issues: list[Finding],
) -> str:
    design = submission.design.model_dump(mode="json", exclude_none=True, by_alias=True)
    parts = [
        "# Requirements",
        json.dumps(submission.requirements.model_dump(mode="json", exclude_none=True), **COMPACT),
        "# Calculated numbers for the original design",
        metrics.headline(),
        "# Original design",
        wrap_untrusted(json.dumps(design, **COMPACT)),
        "# Findings to fix",
        _finding_lines(findings),
    ]
    if open_issues:
        parts += [
            "# Still open after the previous redesign round (fix these now)",
            _finding_lines(open_issues),
        ]
    return "\n".join(parts)


def propose_candidates(
    submission: DesignSubmission,
    findings: list[Finding],
    metrics: DesignMetrics,
    open_issues: list[Finding] | None = None,
    *,
    measure_many: Callable[[list[ComponentGraph]], list[DesignMetrics]] | None = None,
    keys: ProviderKeys | None = None,
    router: ModelRouter | None = None,
) -> ArchitectResult:
    """`measure_many` computes metrics for a batch of designs (the workflow passes the MCP
    calculator client; default = the calculators in-process)."""
    measure_many = measure_many or (
        lambda designs: [measure_design(d, submission.requirements) for d in designs]
    )
    call = call_structured(
        ROLE,
        ArchitectDraft,
        load_prompt("architect_agent"),
        build_user_message(submission, findings, metrics, open_issues or []),
        keys=keys,
        router=router,
    )
    applied, rejected = [], []
    for proposal in call.output.candidates:
        try:
            applied.append((proposal, apply_design_patch(submission.design, proposal.patch)))
        except PatchError as exc:
            rejected.append(f"'{proposal.name}': {exc}")
    measured = measure_many([design for _, design in applied]) if applied else []
    candidates = [
        CandidateDesign(
            name=proposal.name,
            approach=proposal.approach,
            design=design,
            changes=proposal.changes,
            trade_offs=proposal.trade_offs,
            metrics=m,
        )
        for (proposal, design), m in zip(applied, measured, strict=True)
    ]
    return ArchitectResult(candidates, rejected, call.model, call.tokens)
