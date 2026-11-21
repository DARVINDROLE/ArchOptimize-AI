"""The final answer of a review. Every reviewer (baseline or multi-agent) returns this,
so the evaluation can score them the same way.

Step 5 adds pillar scores; Step 6 adds the revised design.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from archoptimize.schemas.finding import Finding


class Verdict(StrEnum):
    APPROVE = "approve"
    APPROVE_WITH_CHANGES = "approve_with_changes"
    REJECT = "reject"


class ReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    summary: str = Field(default="", max_length=3000)
    findings: list[Finding] = Field(default_factory=list)
    requirement_conflicts: list[str] = Field(
        default_factory=list,
        description="Requirements that cannot all be met together, e.g. '99.999 % for $100/month'.",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Facts the review had to assume because they were missing.",
    )
    input_flagged: bool = Field(
        default=False, description="True if the input guard suspected a prompt-injection attempt."
    )
    tokens_used: int | None = Field(default=None, ge=0)
