"""State shared by the workflow nodes.

LangGraph passes one state dict from node to node. Fields marked with a reducer
(`Annotated[list, operator.add]`) are *appended to* when nodes write them — that is how the
parallel reviewers each add their own review, and how redesign rounds accumulate.

Secrets never go in the state: API keys travel in the run config (WorkflowDeps).
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from typing import Annotated, TypedDict

from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter
from archoptimize.retrieval.pillar_retriever import PillarRetriever
from archoptimize.schemas import (
    ComponentGraph,
    DesignSubmission,
    Finding,
    GuardResult,
    Pillar,
    PillarReview,
    ReviewResult,
)
from archoptimize.schemas.candidate_design import CandidateDesign, DesignChange
from archoptimize.schemas.design_metrics import DesignMetrics, ToolCallRecord

MAX_REDESIGN_ROUNDS = 2


class ReviewState(TypedDict, total=False):
    submission: DesignSubmission
    guard: GuardResult
    pillars: list[Pillar]
    original_metrics: DesignMetrics  # from the calculator MCP tools
    tool_calls: Annotated[list[ToolCallRecord], operator.add]
    pillar_reviews: Annotated[list[PillarReview], operator.add]
    warnings: Annotated[list[str], operator.add]
    events: Annotated[list[str], operator.add]  # human-readable progress log
    result: ReviewResult  # the board's review of the ORIGINAL design (from the Chair)

    # --- redesign loop (Architect → Critic → re-review), at most MAX_REDESIGN_ROUNDS ---
    redesign_round: int
    current_design: ComponentGraph  # the design the next Architect round starts from
    candidates: list[CandidateDesign]  # options of the latest round
    winner: CandidateDesign
    critic_rationale: str
    design_changes: Annotated[list[DesignChange], operator.add]
    open_issues: list[Finding]  # blocking findings the re-review still found
    agent_models: Annotated[list[tuple[str, str]], operator.add]
    extra_tokens: Annotated[list[int], operator.add]


class PillarTask(TypedDict):
    """Payload sent to one parallel reviewer."""

    submission: DesignSubmission
    pillar: Pillar
    calculated: str  # headline numbers from the calculators


@dataclass(frozen=True)
class WorkflowDeps:
    """Per-run dependencies, passed via config["configurable"]["deps"]."""

    keys: ProviderKeys
    retriever: PillarRetriever | None
    router: ModelRouter | None = None
    use_guard_model: bool = True
    redesign: bool = True  # False = review only (no Architect/Critic loop)
