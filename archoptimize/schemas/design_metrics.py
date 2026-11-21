"""Calculated numbers for a design (produced by archoptimize.calculators, never by the LLM)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CostLine(BaseModel):
    component_id: str
    description: str
    monthly_usd: float


class CostEstimate(BaseModel):
    total_monthly_usd: float
    peak_monthly_usd: float = Field(description="With autoscaled fleets at their maximum size.")
    lines: list[CostLine]
    unpriced_component_ids: list[str] = Field(description="Components we could not price.")
    budget_usd: float | None = None
    within_budget: bool | None = None
    basis: str = ""


class AvailabilityEstimate(BaseModel):
    estimated_percent: float
    slo_percent: float | None
    meets_slo: bool | None
    per_component_percent: dict[str, float]
    weakest_component_id: str | None


class CapacityCheck(BaseModel):
    peak_rps: int | None
    bottleneck_component_id: str | None
    capacity_rps: float | None
    meets_peak: bool | None
    per_component_rps: dict[str, float]


class DesignMetrics(BaseModel):
    cost: CostEstimate
    availability: AvailabilityEstimate
    capacity: CapacityCheck

    def headline(self) -> str:
        """One line for prompts and the UI."""
        parts = [
            f"cost ≈ ${self.cost.total_monthly_usd:,.0f}/month"
            + (
                f" (budget ${self.cost.budget_usd:,.0f})"
                if self.cost.budget_usd is not None
                else ""
            ),
            f"availability ≈ {self.availability.estimated_percent:.3f} %"
            + (
                f" (SLO {self.availability.slo_percent} %)"
                if self.availability.slo_percent is not None
                else ""
            ),
        ]
        if self.capacity.capacity_rps is not None:
            parts.append(
                f"capacity ≈ {self.capacity.capacity_rps:,.0f} RPS"
                + (f" (peak {self.capacity.peak_rps:,})" if self.capacity.peak_rps else "")
            )
        return "; ".join(parts)


class ToolCallRecord(BaseModel):
    """One calculator call, shown in the UI trace ("numbers come from tools")."""

    tool: str
    via: str  # "mcp" or "local fallback"
    summary: str
    seconds: float
