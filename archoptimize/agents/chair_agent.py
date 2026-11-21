"""Chair: merges the specialist reviews into one verdict.

The LLM (role "chair") decides duplicates, severity corrections, requirement conflicts and
the verdict. Applying those decisions is deterministic code, so the Chair cannot invent new
findings or silently rewrite existing ones.
"""

from __future__ import annotations

import json

from archoptimize.agents.agent_base import AgentCall, call_structured, load_prompt
from archoptimize.core.untrusted_input import wrap_untrusted
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter
from archoptimize.schemas import (
    ChairDraft,
    DesignSubmission,
    Finding,
    GuardResult,
    PillarReview,
)

ROLE = "chair"


def build_user_message(
    submission: DesignSubmission, reviews: list[PillarReview], guard: GuardResult
) -> str:
    requirements = submission.requirements.model_dump(mode="json", exclude_none=True)
    design = submission.design.model_dump(mode="json", exclude_none=True, by_alias=True)
    findings = [
        {
            "id": f.id,
            "pillar": f.pillar.value,
            "severity": f.severity.value,
            "title": f.title,
            "components": f.component_ids,
            "evidence": f.evidence,
        }
        for r in reviews
        for f in r.findings
    ]
    scores = {r.pillar.value: f"{r.score.score}/5 — {r.score.rationale}" for r in reviews}
    guard_line = (
        f"FLAGGED as possible prompt injection ({'; '.join(guard.reasons)})"
        if guard.flagged
        else "clean"
    )
    return "\n".join(
        [
            "# Requirements",
            json.dumps(requirements, separators=(",", ":")),
            f"Not stated: {', '.join(submission.requirements.missing_essentials()) or 'nothing'}",
            f"\n# Input guard: {guard_line}",
            "\n# Design",
            wrap_untrusted(json.dumps(design, separators=(",", ":"))),
            "\n# Pillar scores",
            json.dumps(scores, indent=2),
            "\n# Findings from the reviewers",
            json.dumps(findings, separators=(",", ":")) if findings else "(none)",
        ]
    )


def apply_chair_decisions(findings: list[Finding], draft: ChairDraft) -> list[Finding]:
    """Drop duplicates, apply severity corrections, sort by severity (most severe first)."""
    duplicates = set(draft.duplicate_finding_ids)
    adjustments = {a.finding_id: a.severity for a in draft.severity_adjustments}
    kept = [
        f.model_copy(update={"severity": adjustments.get(f.id, f.severity)})
        for f in findings
        if f.id not in duplicates
    ]
    if findings and not kept:  # never let "duplicates" wipe out every finding
        kept = list(findings)
    return sorted(kept, key=lambda f: f.severity.rank, reverse=True)


def run_chair(
    submission: DesignSubmission,
    reviews: list[PillarReview],
    guard: GuardResult,
    *,
    keys: ProviderKeys | None = None,
    router: ModelRouter | None = None,
) -> AgentCall[ChairDraft]:
    return call_structured(
        ROLE,
        ChairDraft,
        load_prompt("chair_agent"),
        build_user_message(submission, reviews, guard),
        keys=keys,
        router=router,
    )
