"""What the design must achieve. Every field is optional because real briefs are often
incomplete; `missing_essentials()` tells the review what it had to work without."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ComplianceStandard(StrEnum):
    PCI_DSS = "pci_dss"
    HIPAA = "hipaa"
    GDPR = "gdpr"
    SOC2 = "soc2"


ESSENTIAL_FIELDS = ("availability_slo_percent", "peak_rps", "monthly_budget_usd")


class Requirements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    availability_slo_percent: float | None = Field(
        default=None, gt=0, lt=100, description="Target uptime, e.g. 99.9 (must be below 100)."
    )
    peak_rps: int | None = Field(default=None, ge=1, description="Peak requests per second.")
    p95_latency_ms: int | None = Field(default=None, ge=1, description="95th percentile latency.")
    monthly_budget_usd: float | None = Field(default=None, ge=0)
    rpo_minutes: int | None = Field(default=None, ge=0, description="Max acceptable data loss.")
    rto_minutes: int | None = Field(default=None, ge=0, description="Max acceptable downtime.")
    compliance: list[ComplianceStandard] = Field(default_factory=list)
    region: str = Field(default="us-east-1", pattern=r"^[a-z]{2}(-[a-z]+)+-\d$")

    def missing_essentials(self) -> list[str]:
        return [name for name in ESSENTIAL_FIELDS if getattr(self, name) is None]

    def requires(self, standard: ComplianceStandard) -> bool:
        return standard in self.compliance
