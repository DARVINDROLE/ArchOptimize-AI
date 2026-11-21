"""Redesign proposals (Architect) and their evaluation (Critic).

Tree of Thoughts: instead of one fix, the Architect proposes several distinct candidate
designs in ONE call; the Critic compares them against a rubric and calculated numbers and
picks the winner, which is then re-reviewed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from archoptimize.schemas.component_graph import ComponentGraph
from archoptimize.schemas.design_metrics import DesignMetrics
from archoptimize.schemas.design_patch import DesignPatch


class DesignChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(max_length=600, description="What changes and why.")
    finding_ids: list[str] = Field(
        description="Ids of the review findings this change fixes (e.g. REL-1)."
    )


class CandidateProposal(BaseModel):
    """One option as written by the Architect LLM."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=80, description="Short label, e.g. 'Multi-AZ + autoscaling'.")
    approach: str = Field(max_length=800, description="The idea of this option in 1-3 sentences.")
    patch: DesignPatch = Field(description="Exact changes to apply to the original design.")
    changes: list[DesignChange] = Field(description="Every change, tagged with finding ids.")
    trade_offs: str = Field(max_length=1000, description="What this option costs or gives up.")


class ArchitectDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateProposal] = Field(
        min_length=2,
        max_length=3,
        description="Three genuinely different options: minimal fix, balanced, robust.",
    )


class CandidateDesign(BaseModel):
    """A proposal after the patch was applied and the result measured."""

    model_config = ConfigDict(extra="forbid")

    name: str
    approach: str
    design: ComponentGraph
    changes: list[DesignChange]
    trade_offs: str
    metrics: DesignMetrics
    critic_score: int | None = None


class CandidateScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_name: str
    meets_requirements: bool = Field(
        description="Meets SLO, peak RPS and budget according to the calculated numbers."
    )
    fixed_finding_ids: list[str] = Field(description="Findings this candidate really fixes.")
    score: int = Field(ge=1, le=10, description="Overall rubric score, 10 = best.")
    strengths: str = Field(max_length=800)
    weaknesses: str = Field(max_length=800)


class CriticDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: list[CandidateScore]
    winner_name: str = Field(description="`candidate_name` of the best candidate.")
    rationale: str = Field(max_length=2000, description="Why the winner beats the others.")
