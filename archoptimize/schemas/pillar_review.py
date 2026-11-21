"""Outputs of the specialist reviewers (one per pillar) and of the input guard."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from archoptimize.schemas.doc_chunk import DocChunk
from archoptimize.schemas.finding import Finding, Pillar


class PillarReviewDraft(BaseModel):
    """What a pillar reviewer LLM fills in (structured output)."""

    model_config = ConfigDict(extra="forbid")

    findings: list[Finding] = Field(
        description="Problems for YOUR pillar only, most important first (at most 6)."
    )
    score: int = Field(
        ge=1,
        le=5,
        description="How well the design does on your pillar: 5 excellent, 4 good, "
        "3 acceptable with gaps, 2 serious gaps, 1 fails the requirements.",
    )
    score_rationale: str = Field(max_length=1500, description="One or two sentences.")
    assumptions: list[str] = Field(description="Missing facts you had to assume.")


class PillarScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pillar: Pillar
    score: int = Field(ge=1, le=5)
    rationale: str = ""


class PillarReview(BaseModel):
    """A finished pillar review: validated findings + score + provenance."""

    model_config = ConfigDict(extra="forbid")

    pillar: Pillar
    findings: list[Finding]
    score: PillarScore
    assumptions: list[str] = Field(default_factory=list)
    sources: list[DocChunk] = Field(default_factory=list)
    uncited_finding_ids: list[str] = Field(default_factory=list)
    model: str = ""
    tokens: int | None = None


class GuardResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flagged: bool
    max_score: float = Field(ge=0, le=1, description="Highest injection probability seen.")
    reasons: list[str] = Field(default_factory=list)
    model: str | None = None  # None when only the rule-based check ran
