"""A single review finding. Reviewers return a list of these (structured output).

Length limits are generous on purpose: Groq validates structured output strictly, and a
too-tight limit makes a good answer fail as invalid JSON.

Field descriptions are sent to the LLM as part of the JSON schema, so they are written
as instructions.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Pillar(StrEnum):
    """AWS Well-Architected pillars, plus compliance (e.g. PCI DSS)."""

    SECURITY = "security"
    RELIABILITY = "reliability"
    COST_OPTIMIZATION = "cost_optimization"
    PERFORMANCE_EFFICIENCY = "performance_efficiency"  # our "Scalability" reviewer
    OPERATIONAL_EXCELLENCE = "operational_excellence"
    SUSTAINABILITY = "sustainability"
    COMPLIANCE = "compliance"


class Severity(StrEnum):
    CRITICAL = "critical"  # violates a hard requirement or compliance rule
    HIGH = "high"  # likely to break the SLO / budget / security
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

    @property
    def rank(self) -> int:
        """Higher = more severe; use for sorting."""
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40, description="Short id, e.g. 'REL-001'.")
    pillar: Pillar
    severity: Severity
    title: str = Field(min_length=1, max_length=200, description="One-line summary.")
    component_ids: list[str] = Field(
        default_factory=list,
        description="Ids of the affected components from the design (empty = whole system).",
    )
    evidence: str = Field(
        min_length=1,
        max_length=2000,
        description="Why this is a problem, pointing at concrete facts in the design.",
    )
    recommendation: str = Field(min_length=1, max_length=2000, description="What to change.")
    citation_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Ids of the retrieved documentation chunks that support this finding.",
    )
