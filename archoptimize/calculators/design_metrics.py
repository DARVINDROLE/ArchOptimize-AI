"""All numbers for one design in one call: monthly cost, availability, capacity.

Used to compare the original design with each candidate redesign (Critic), and shown in
the UI's "Cost & trade-offs" tab.
"""

from __future__ import annotations

from archoptimize.calculators.availability import estimate_availability
from archoptimize.calculators.capacity import check_capacity
from archoptimize.calculators.monthly_cost import estimate_monthly_cost
from archoptimize.calculators.price_source import PriceSource
from archoptimize.schemas import ComponentGraph, Requirements
from archoptimize.schemas.design_metrics import DesignMetrics


def measure_design(
    graph: ComponentGraph, req: Requirements, prices: PriceSource | None = None
) -> DesignMetrics:
    return DesignMetrics(
        cost=estimate_monthly_cost(graph, req, prices),
        availability=estimate_availability(graph, req.availability_slo_percent),
        capacity=check_capacity(graph, req),
    )
