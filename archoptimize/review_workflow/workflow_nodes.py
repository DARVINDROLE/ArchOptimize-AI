"""Workflow nodes: thin adapters between the LangGraph state and the agents."""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langgraph.types import Send

from archoptimize.agents.architect_agent import propose_candidates
from archoptimize.agents.chair_agent import apply_chair_decisions, run_chair
from archoptimize.agents.critic_agent import judge_candidates
from archoptimize.agents.input_guard import check_input
from archoptimize.agents.reviewer_selector import select_pillars
from archoptimize.agents.reviewers import REVIEWERS, run_pillar_review
from archoptimize.core.secret_redaction import redact
from archoptimize.llm.quota_messages import is_daily_limit
from archoptimize.mcp_server.calculator_client import measure_designs_via_mcp
from archoptimize.review_workflow.workflow_state import (
    MAX_REDESIGN_ROUNDS,
    PillarTask,
    ReviewState,
    WorkflowDeps,
)
from archoptimize.schemas import (
    ChairDraft,
    Finding,
    PillarReview,
    ReviewResult,
    Severity,
    Verdict,
)
from archoptimize.schemas.candidate_design import CandidateDesign

log = logging.getLogger(__name__)


def _deps(config: RunnableConfig) -> WorkflowDeps:
    return config["configurable"]["deps"]


_PROVIDER_LIMIT = {"groq": "Groq tokens per day", "openrouter": "OpenRouter free-models-per-day"}


def _warning(text: str, limit: int = 300) -> str:
    """Redact and shorten an error for the report, but never cut away the fact that a
    provider hit its DAILY limit: the UI uses it to tell the user to wait ~24 h, not minutes.
    (An AllModelsFailedError lists one '- provider:model: error' line per model tried.)"""
    text = redact(text)
    hit = [
        label
        for provider, label in _PROVIDER_LIMIT.items()
        if any(is_daily_limit(line) and f"{provider}:" in line for line in text.splitlines())
    ]
    if not hit and is_daily_limit(text):
        hit = [_PROVIDER_LIMIT["groq"]]
    if not hit:
        return text[:limit]
    marker = f" … [rate limit: daily free-tier limit reached: {' + '.join(hit)}]"
    return text[: limit - len(marker)] + marker


def guard_node(state: ReviewState, config: RunnableConfig) -> dict:
    deps = _deps(config)
    guard = check_input(
        state["submission"], keys=deps.keys, router=deps.router, use_model=deps.use_guard_model
    )
    status = f"FLAGGED ({'; '.join(guard.reasons)})" if guard.flagged else "clean"
    return {"guard": guard, "events": [f"Input guard: {status}"]}


def select_node(state: ReviewState) -> dict:
    submission = state["submission"]
    pillars = select_pillars(submission)
    names = ", ".join(REVIEWERS[p].display_name for p in pillars)
    (metrics,), record = measure_designs_via_mcp([submission.design], submission.requirements)
    return {
        "pillars": pillars,
        "original_metrics": metrics,
        "tool_calls": [record],
        "events": [
            f"Reviewers selected: {names}",
            f"Calculators ({record.via}): {metrics.headline()}",
        ],
    }


def fan_out_to_reviewers(state: ReviewState) -> list[Send]:
    """One parallel branch per selected pillar (LangGraph 'Send' = map step)."""
    return [
        Send(
            "pillar_review",
            PillarTask(
                submission=state["submission"],
                pillar=p,
                calculated=state["original_metrics"].headline(),
            ),
        )
        for p in state["pillars"]
    ]


def pillar_review_node(task: PillarTask, config: RunnableConfig) -> dict:
    deps = _deps(config)
    spec = REVIEWERS[task["pillar"]]
    try:
        review = run_pillar_review(
            spec,
            task["submission"],
            retriever=deps.retriever,
            calculated=task.get("calculated"),
            keys=deps.keys,
            router=deps.router,
        )
    except Exception as exc:  # one failing reviewer must not sink the whole review
        message = _warning(f"{spec.display_name} failed: {type(exc).__name__}: {exc}")
        log.warning(message)
        return {"warnings": [message], "events": [message]}
    event = (
        f"{spec.display_name}: {len(review.findings)} finding(s), "
        f"score {review.score.score}/5 ({review.model})"
    )
    return {"pillar_reviews": [review], "events": [event]}


def chair_node(state: ReviewState, config: RunnableConfig) -> dict:
    deps = _deps(config)
    order = {p: i for i, p in enumerate(state["pillars"])}
    reviews: list[PillarReview] = sorted(
        state.get("pillar_reviews", []), key=lambda r: order.get(r.pillar, 99)
    )
    all_findings = [f for r in reviews for f in r.findings]
    chair_warnings: list[str] = []
    try:
        call = run_chair(
            state["submission"], reviews, state["guard"], keys=deps.keys, router=deps.router
        )
        draft, chair_model, chair_tokens = call.output, call.model, call.tokens
    except Exception as exc:  # e.g. the daily token limit: still return a usable review
        draft = fallback_chair_draft(all_findings, state["guard"].flagged)
        chair_model, chair_tokens = "rule-based fallback", None
        chair_warnings.append(_warning(f"Chair failed, rule-based verdict used: {exc}"))
    findings = apply_chair_decisions(all_findings, draft)
    kept_ids = {f.id for f in findings}

    sources = {c.chunk_id: c for r in reviews for c in r.sources}
    models = {"Input guard": state["guard"].model or "rules only"}
    models |= {f"{r.pillar.value} reviewer": r.model for r in reviews}
    models["Chair"] = chair_model
    tokens = [t for t in [*(r.tokens for r in reviews), chair_tokens] if t is not None]
    assumptions = list(
        dict.fromkeys([*draft.assumptions, *(a for r in reviews for a in r.assumptions)])
    )

    result = ReviewResult(
        verdict=draft.verdict,
        summary=draft.summary,
        findings=findings,
        pillar_scores=[r.score for r in reviews],
        requirement_conflicts=draft.requirement_conflicts,
        assumptions=assumptions[:12],
        input_flagged=state["guard"].flagged,
        guard_reasons=state["guard"].reasons,
        sources=list(sources.values()),
        uncited_finding_ids=[i for r in reviews for i in r.uncited_finding_ids if i in kept_ids],
        warnings=[*state.get("warnings", []), *chair_warnings],
        models_used=models,
        tokens_used=sum(tokens) if tokens else None,
    )
    return {
        "result": result,
        "current_design": state["submission"].design,
        "warnings": chair_warnings,
        "events": [*chair_warnings, f"Chair: verdict {draft.verdict.value} ({chair_model})"],
    }


def fallback_chair_draft(findings: list[Finding], input_flagged: bool) -> ChairDraft:
    """Verdict straight from the severities, used only when the Chair LLM is unavailable."""
    worst = max((f.severity.rank for f in findings), default=-1)
    if worst >= Severity.CRITICAL.rank:
        verdict = Verdict.REJECT
    elif worst >= Severity.MEDIUM.rank or input_flagged:
        verdict = Verdict.APPROVE_WITH_CHANGES
    else:
        verdict = Verdict.APPROVE
    return ChairDraft(
        summary=(
            "The Chair model was unavailable, so this verdict was computed from the reviewers' "
            f"finding severities ({len(findings)} finding(s)). Duplicates were not merged."
        ),
        duplicate_finding_ids=[],
        severity_adjustments=[],
        requirement_conflicts=[],
        assumptions=[],
        verdict=verdict,
    )


# --------------------------------------------------------------------------------------
# Redesign loop: Architect (3 options) → Critic (pick one) → re-review → maybe repeat
# --------------------------------------------------------------------------------------

BLOCKING = (Severity.CRITICAL, Severity.HIGH)


def after_chair(state: ReviewState, config: RunnableConfig) -> str:
    """Every review gets 3 redesign options: fixes when the board found problems, optional
    improvements (cost, resilience, performance) when the design is already approved."""
    return "architect" if _deps(config).redesign else "finalize"


def architect_node(state: ReviewState, config: RunnableConfig) -> dict:
    deps = _deps(config)
    round_no = state.get("redesign_round", 0) + 1
    base = state["submission"].model_copy(update={"design": state["current_design"]})
    records = []

    def measure_many(designs):
        metrics, record = measure_designs_via_mcp(designs, base.requirements)
        records.append(record)
        return metrics

    base_metrics = state["winner"].metrics if state.get("winner") else state["original_metrics"]
    try:
        proposal = propose_candidates(
            base,
            state["result"].findings,
            base_metrics,
            state.get("open_issues", []),
            measure_many=measure_many,
            keys=deps.keys,
            router=deps.router,
        )
    except Exception as exc:
        message = _warning(f"Architect failed: {type(exc).__name__}: {exc}")
        return {
            "redesign_round": round_no,
            "candidates": [],
            "warnings": [message],
            "events": [message],
        }
    warnings = [f"Architect proposal dropped: {r}" for r in proposal.rejected]
    names = ", ".join(c.name for c in proposal.candidates) or "none usable"
    return {
        "redesign_round": round_no,
        "candidates": proposal.candidates,
        "warnings": warnings,
        "agent_models": [("Architect", proposal.model)],
        "extra_tokens": [proposal.tokens or 0],
        "tool_calls": records,
        "events": [
            f"Architect (round {round_no}): {len(proposal.candidates)} candidates — {names}"
        ],
    }


def after_architect(state: ReviewState) -> str:
    return "critic" if state.get("candidates") else "finalize"


def _fallback_winner(candidates: list[CandidateDesign]) -> CandidateDesign:
    """If the Critic is unavailable: most requirements met, then cheapest."""

    def met(c: CandidateDesign) -> int:
        m = c.metrics
        return sum(
            bool(x) for x in (m.availability.meets_slo, m.capacity.meets_peak, m.cost.within_budget)
        )

    return sorted(candidates, key=lambda c: (-met(c), c.metrics.cost.total_monthly_usd))[0]


def critic_node(state: ReviewState, config: RunnableConfig) -> dict:
    deps = _deps(config)
    candidates = state["candidates"]
    try:
        verdict = judge_candidates(
            state["submission"],
            state["result"].findings,
            candidates,
            keys=deps.keys,
            router=deps.router,
        )
        winner, rationale = verdict.winner, verdict.draft.rationale
        extra = {"agent_models": [("Critic", verdict.model)], "extra_tokens": [verdict.tokens or 0]}
        event = f"Critic: picked '{winner.name}' ({verdict.model})"
    except Exception as exc:
        winner = _fallback_winner(candidates)
        rationale = (
            "Critic unavailable; picked the option meeting most requirements at lowest cost."
        )
        message = _warning(f"Critic failed, rule-based pick used: {type(exc).__name__}: {exc}")
        extra = {"warnings": [message]}
        event = f"Critic unavailable → rule-based pick '{winner.name}'"
    return {
        "winner": winner,
        "critic_rationale": rationale,
        "current_design": winner.design,
        "design_changes": winner.changes,
        "events": [event, f"  {winner.name}: {winner.metrics.headline()}"],
        **extra,
    }


def rereview_node(state: ReviewState, config: RunnableConfig) -> dict:
    """Re-check the winner with the reviewers of the pillars that had serious findings."""
    deps = _deps(config)
    findings = state["result"].findings
    pillars = [
        p
        for p in state["pillars"]
        if any(f.pillar is p and f.severity in BLOCKING for f in findings)
    ]
    pillars = pillars or [p for p in state["pillars"] if any(f.pillar is p for f in findings)]
    revised = state["submission"].model_copy(update={"design": state["winner"].design})
    open_issues: list[Finding] = []
    events, warnings, models, tokens = [], [], [], []
    for pillar in pillars:
        spec = REVIEWERS[pillar]
        try:
            review = run_pillar_review(
                spec,
                revised,
                retriever=deps.retriever,
                calculated=state["winner"].metrics.headline(),
                keys=deps.keys,
                router=deps.router,
            )
        except Exception as exc:
            warnings.append(_warning(f"Re-review by {spec.display_name} failed: {exc}"))
            continue
        blocking = [f for f in review.findings if f.severity in BLOCKING]
        open_issues += blocking
        models.append((f"{pillar.value} re-review", review.model))
        tokens.append(review.tokens or 0)
        events.append(f"Re-review ({spec.display_name}): {len(blocking)} blocking issue(s) left")
    return {
        "open_issues": open_issues,
        "warnings": warnings,
        "events": events,
        "agent_models": models,
        "extra_tokens": tokens,
    }


def after_rereview(state: ReviewState) -> str:
    if state.get("open_issues") and state.get("redesign_round", 0) < MAX_REDESIGN_ROUNDS:
        return "architect"
    return "finalize"


def redesign_note(state: ReviewState, redesign_enabled: bool) -> str:
    """Tell the user WHY there is or is not a revised design (never a misleading silence)."""
    result = state["result"]
    if state.get("winner") is not None:
        pick = state["winner"].name
        if result.verdict is Verdict.APPROVE:
            return (
                "The design already meets its requirements: the 3 options are optional "
                f"improvements. The Critic recommends '{pick}'."
            )
        rounds = state.get("redesign_round", 0)
        left = len(state.get("open_issues", []))
        tail = f"{left} serious issue(s) still open" if left else "no serious issues left"
        return f"The Critic picked '{pick}' ({rounds} redesign round(s); {tail})."
    if not redesign_enabled:
        return "Redesign was switched off for this run."
    # the Architect ran but produced nothing usable: say so, whatever the verdict
    if state.get("redesign_round", 0) > 0:
        reasons = [w for w in state.get("warnings", []) if w.startswith(("Architect", "Critic"))]
        if any(is_daily_limit(r) for r in reasons):
            both = any("openrouter" in r.lower() for r in reasons)
            return (
                "Redesign could not be completed: today's free-tier budget is used up for the "
                "Architect's models"
                + (" on both Groq and OpenRouter" if both else " on your Groq key")
                + ". It resets within ~24 hours"
                + (
                    "."
                    if both
                    else "; adding an OpenRouter key gives the Architect more "
                    "free models to fall back on."
                )
            )
        why = f" ({reasons[-1][:160]})" if reasons else ""
        return (
            f"Redesign could not be completed{why}. This is usually a temporary free-tier "
            "rate limit: please try again in a few minutes."
        )
    if result.verdict is Verdict.APPROVE:
        return "No redesign needed: the design meets its stated requirements."
    if result.requirement_conflicts:
        return (
            "No redesign proposed: the requirements conflict with each other (see Verdict). "
            "Relax one of them (e.g. budget or SLO), then review again."
        )
    return (
        "No redesign proposed: the review found no concrete component-level flaw to fix — the "
        "verdict is driven by missing information. Add the missing details (see Assumptions) "
        "and review again."
    )


def finalize_node(state: ReviewState, config: RunnableConfig) -> dict:
    result = state["result"]
    update: dict = {
        "original_metrics": state["original_metrics"],
        "tool_calls": state.get("tool_calls", []),
        "warnings": state.get("warnings", []),
        "redesign_note": redesign_note(state, _deps(config).redesign),
    }
    winner = state.get("winner")
    if winner is not None:
        models = dict(result.models_used)
        models.update(dict(state.get("agent_models", [])))
        extra = sum(state.get("extra_tokens", []))
        update |= {
            "revised_design": winner.design,
            "revised_metrics": winner.metrics,
            "design_changes": state.get("design_changes", []),
            "candidates": state.get("candidates", []),
            "critic_rationale": state.get("critic_rationale", ""),
            "remaining_issues": state.get("open_issues", []),
            "redesign_rounds": state.get("redesign_round", 0),
            "models_used": models,
            "tokens_used": (result.tokens_used or 0) + extra,
        }
    done = "with redesign" if winner is not None else "without redesign"
    return {"result": result.model_copy(update=update), "events": [f"Review complete ({done})"]}
