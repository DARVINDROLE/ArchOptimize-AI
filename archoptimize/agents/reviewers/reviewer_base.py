"""Shared logic of every pillar reviewer: retrieve → prompt → structured findings → checks.

1. retrieve the top-k chunks of THIS pillar's documentation for this design
2. ask the LLM (the reviewer's own role, e.g. "security_reviewer") for findings + a 1-5
   pillar score, citing chunk ids
3. post-process deterministically:
   - every finding gets this reviewer's pillar and a unique id (SEC-1, SEC-2, ...)
   - component ids the model invented are dropped
   - citations that were not retrieved are removed (citation validator)
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from archoptimize.agents.agent_base import call_structured, load_prompt, render_prompt
from archoptimize.core.untrusted_input import wrap_untrusted
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter
from archoptimize.retrieval.citation_validator import validate_citations
from archoptimize.retrieval.pillar_retriever import PillarRetriever
from archoptimize.retrieval.review_evidence import PILLAR_FOCUS, design_facts, format_evidence
from archoptimize.schemas import (
    DesignSubmission,
    Finding,
    Pillar,
    PillarReview,
    PillarReviewDraft,
    PillarScore,
)
from archoptimize.schemas.doc_chunk import DocChunk

EVIDENCE_TOP_K = 3  # small on purpose: Groq free tier allows ~8k tokens/minute per model
COMPACT = {"separators": (",", ":")}  # compact JSON = fewer tokens than indented JSON


@dataclass(frozen=True)
class ReviewerSpec:
    pillar: Pillar
    display_name: str  # e.g. "Security reviewer"
    id_prefix: str  # e.g. "SEC"
    prompt_name: str  # agents/prompts/<prompt_name>.md holds the pillar checklist

    @property
    def role(self) -> str:
        """LLM role in llm_roles.yaml (same name as the agent module)."""
        return self.prompt_name


def build_user_message(
    submission: DesignSubmission, evidence: list[DocChunk], calculated: str | None = None
) -> str:
    requirements = submission.requirements.model_dump(mode="json", exclude_none=True)
    missing = submission.requirements.missing_essentials()
    design = submission.design.model_dump(mode="json", exclude_none=True, by_alias=True)
    parts = [
        "# Requirements",
        json.dumps(requirements, **COMPACT),
        f"Not stated: {', '.join(missing)}" if missing else "",
        "",
        "# Design",
        wrap_untrusted(json.dumps(design, **COMPACT)),
        "",
        "# Reference documentation",
        format_evidence(evidence) if evidence else "(none available)",
    ]
    return "\n".join(parts)


def _normalise_findings(
    findings: list[Finding], spec: ReviewerSpec, known_components: set[str]
) -> list[Finding]:
    return [
        f.model_copy(
            update={
                "id": f"{spec.id_prefix}-{n}",
                "pillar": spec.pillar,
                "component_ids": [c for c in f.component_ids if c in known_components],
            }
        )
        for n, f in enumerate(findings, start=1)
    ]


def run_pillar_review(
    spec: ReviewerSpec,
    submission: DesignSubmission,
    *,
    retriever: PillarRetriever | None,
    calculated: str | None = None,
    keys: ProviderKeys | None = None,
    router: ModelRouter | None = None,
) -> PillarReview:
    evidence: list[DocChunk] = []
    if retriever is not None:
        query = f"{PILLAR_FOCUS[spec.pillar]}. {design_facts(submission)}"
        evidence = [h.chunk for h in retriever.retrieve(query, spec.pillar, k=EVIDENCE_TOP_K)]

    system = render_prompt(
        load_prompt("reviewer_base"),
        pillar_name=spec.display_name,
        pillar_checklist=load_prompt(spec.prompt_name),
    )
    call = call_structured(
        spec.role,
        PillarReviewDraft,
        system,
        build_user_message(submission, evidence, calculated),
        keys=keys,
        router=router,
    )
    known = {c.id for c in submission.design.components}
    findings = _normalise_findings(call.output.findings, spec, known)
    check = validate_citations(findings, {c.chunk_id for c in evidence})
    return PillarReview(
        pillar=spec.pillar,
        findings=check.findings,
        score=PillarScore(
            pillar=spec.pillar, score=call.output.score, rationale=call.output.score_rationale
        ),
        assumptions=call.output.assumptions,
        sources=evidence,
        uncited_finding_ids=check.uncited_finding_ids,
        model=call.model,
        tokens=call.tokens,
    )
