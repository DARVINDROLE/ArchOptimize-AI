"""Single-LLM baseline review: one prompt, one call, structured output.

Step 3: design + requirements only.
Step 4: optionally with retrieved AWS documentation (RAG) that findings must cite.

It is kept for good as the yardstick: every later step (multi-agent, critic loop) must beat
it on the evaluation set.
"""

from __future__ import annotations

import json

from archoptimize.agents.agent_base import call_structured, load_prompt
from archoptimize.core.untrusted_input import wrap_untrusted
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter
from archoptimize.retrieval.citation_validator import validate_citations
from archoptimize.retrieval.pillar_retriever import PillarRetriever
from archoptimize.retrieval.review_evidence import collect_review_evidence, format_evidence
from archoptimize.schemas import DesignSubmission, ReviewDraft, ReviewResult
from archoptimize.schemas.doc_chunk import DocChunk

ROLE = "baseline_reviewer"


def build_user_message(submission: DesignSubmission, evidence: list[DocChunk] | None = None) -> str:
    requirements = submission.requirements.model_dump(mode="json", exclude_none=True)
    missing = submission.requirements.missing_essentials()
    design = submission.design.model_dump(mode="json", exclude_none=True, by_alias=True)
    parts = [
        "# Requirements",
        json.dumps(requirements, indent=2),
        f"Not stated: {', '.join(missing)}" if missing else "",
        "",
        "# Design",
        wrap_untrusted(json.dumps(design, indent=2)),
    ]
    if evidence:
        parts += ["", "# Reference documentation", format_evidence(evidence)]
    return "\n".join(parts)


def _keep_known_components(draft: ReviewDraft, submission: DesignSubmission) -> ReviewDraft:
    """Drop component ids the model invented, so scoring and diagrams stay consistent."""
    known = {c.id for c in submission.design.components}
    findings = [
        f.model_copy(update={"component_ids": [i for i in f.component_ids if i in known]})
        for f in draft.findings
    ]
    return draft.model_copy(update={"findings": findings})


def review_baseline(
    submission: DesignSubmission,
    *,
    retriever: PillarRetriever | None = None,
    keys: ProviderKeys | None = None,
    router: ModelRouter | None = None,
) -> ReviewResult:
    evidence = collect_review_evidence(submission, retriever) if retriever else []
    call = call_structured(
        ROLE,
        ReviewDraft,
        load_prompt("baseline_reviewer"),
        build_user_message(submission, evidence),
        keys=keys,
        router=router,
    )
    draft = _keep_known_components(call.output, submission)
    check = validate_citations(draft.findings, {c.chunk_id for c in evidence})
    return ReviewResult(
        verdict=draft.verdict,
        summary=draft.summary,
        findings=check.findings,
        requirement_conflicts=draft.requirement_conflicts,
        assumptions=draft.assumptions,
        input_flagged=draft.suspicious_instructions_found,
        sources=evidence,
        uncited_finding_ids=check.uncited_finding_ids,
        tokens_used=call.tokens,
    )
