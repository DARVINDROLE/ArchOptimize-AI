"""Critic: scores the candidates with a rubric and the calculated numbers, picks a winner.

It runs on a different model family than the Architect (role "critic": a free OpenRouter
model chosen at runtime, or a non-OpenAI Groq model) so the judge is not grading its own
work.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from archoptimize.agents.agent_base import call_structured, load_prompt
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter
from archoptimize.schemas import DesignSubmission, Finding
from archoptimize.schemas.candidate_design import CandidateDesign, CriticDraft

ROLE = "critic"
COMPACT = {"separators": (",", ":")}


@dataclass
class CriticResult:
    winner: CandidateDesign
    draft: CriticDraft
    model: str
    tokens: int | None


def build_user_message(
    submission: DesignSubmission, findings: list[Finding], candidates: list[CandidateDesign]
) -> str:
    blocks = []
    for c in candidates:
        m = c.metrics
        blocks.append(
            {
                "candidate_name": c.name,
                "approach": c.approach,
                "changes": [
                    {"change": ch.description, "fixes": ch.finding_ids} for ch in c.changes
                ],
                "trade_offs": c.trade_offs,
                "calculated": {
                    "monthly_cost_usd": m.cost.total_monthly_usd,
                    "within_budget": m.cost.within_budget,
                    "availability_percent": m.availability.estimated_percent,
                    "meets_slo": m.availability.meets_slo,
                    "capacity_rps": m.capacity.capacity_rps,
                    "meets_peak_rps": m.capacity.meets_peak,
                },
            }
        )
    must_fix = [
        {"id": f.id, "severity": f.severity.value, "title": f.title}
        for f in findings
        if f.severity.rank >= 2
    ]
    return "\n".join(
        [
            "# Requirements",
            json.dumps(
                submission.requirements.model_dump(mode="json", exclude_none=True), **COMPACT
            ),
            "# Findings to fix",
            json.dumps(must_fix, **COMPACT),
            "# Candidates",
            json.dumps(blocks, **COMPACT),
        ]
    )


def _pick(candidates: list[CandidateDesign], draft: CriticDraft) -> CandidateDesign:
    by_name = {c.name.strip().lower(): c for c in candidates}
    chosen = by_name.get(draft.winner_name.strip().lower())
    if chosen:
        return chosen
    # name mismatch: fall back to the highest-scored candidate the critic did name
    scored = sorted(draft.scores, key=lambda s: s.score, reverse=True)
    for s in scored:
        if s.candidate_name.strip().lower() in by_name:
            return by_name[s.candidate_name.strip().lower()]
    return candidates[0]


def judge_candidates(
    submission: DesignSubmission,
    findings: list[Finding],
    candidates: list[CandidateDesign],
    *,
    keys: ProviderKeys | None = None,
    router: ModelRouter | None = None,
) -> CriticResult:
    if not candidates:
        raise ValueError("no candidates to judge")
    call = call_structured(
        ROLE,
        CriticDraft,
        load_prompt("critic_agent"),
        build_user_message(submission, findings, candidates),
        keys=keys,
        router=router,
    )
    scores = {s.candidate_name.strip().lower(): s.score for s in call.output.scores}
    for c in candidates:
        c.critic_score = scores.get(c.name.strip().lower())
    return CriticResult(_pick(candidates, call.output), call.output, call.model, call.tokens)
