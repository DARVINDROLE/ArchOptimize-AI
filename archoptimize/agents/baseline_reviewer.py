"""Single-LLM baseline review (Step 3): one prompt, one call, structured output.

It is kept for good as the yardstick: every later step (RAG, multi-agent, critic loop)
must beat this baseline on the evaluation set.
"""

from __future__ import annotations

import json

from archoptimize.agents.agent_base import call_structured, load_prompt
from archoptimize.core.untrusted_input import wrap_untrusted
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter
from archoptimize.schemas import DesignSubmission, ReviewDraft, ReviewResult

ROLE = "baseline_reviewer"


def build_user_message(submission: DesignSubmission) -> str:
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
    return "\n".join(p for p in parts if p is not None)


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
    keys: ProviderKeys | None = None,
    router: ModelRouter | None = None,
) -> ReviewResult:
    call = call_structured(
        ROLE,
        ReviewDraft,
        load_prompt("baseline_reviewer"),
        build_user_message(submission),
        keys=keys,
        router=router,
    )
    draft = _keep_known_components(call.output, submission)
    return ReviewResult(
        verdict=draft.verdict,
        summary=draft.summary,
        findings=draft.findings,
        requirement_conflicts=draft.requirement_conflicts,
        assumptions=draft.assumptions,
        input_flagged=draft.suspicious_instructions_found,
        tokens_used=call.tokens,
    )
