"""Availability math.

- Series (A calls B synchronously, both must work):  A_total = A_a × A_b
- Parallel (n independent copies, one is enough):    A_total = 1 − (1 − A)^n

Per-component estimates follow public AWS SLA tiers (rounded): a single EC2 instance
99.5 %, Multi-AZ RDS 99.95 % vs single-AZ 99.5 %, Aurora / DynamoDB / ElastiCache Multi-AZ
/ ELB 99.99 %. For CDN and S3 we use typical availability (99.99 %) rather than their
99.9 % credit threshold, which would understate well-built designs.
Copies only count as independent when they are spread over different AZs.
Only components on the synchronous request path count (async consumers are decoupled).
"""

from __future__ import annotations

import re

from archoptimize.schemas import Component, ComponentGraph, ComponentType, EdgeMode
from archoptimize.schemas.design_metrics import AvailabilityEstimate

SINGLE_INSTANCE = 0.995
MANAGED_MULTI_AZ = {
    ComponentType.LOAD_BALANCER: 0.9999,
    ComponentType.API_GATEWAY: 0.9995,
    ComponentType.SERVERLESS_FUNCTION: 0.9995,
    ComponentType.NOSQL_DATABASE: 0.9999,
    ComponentType.OBJECT_STORAGE: 0.9999,
    ComponentType.QUEUE: 0.999,
    ComponentType.STREAM: 0.999,
    ComponentType.CDN: 0.9999,
    ComponentType.WAF: 0.9999,
    ComponentType.DNS: 0.99999,
}
DATABASE_MULTI_AZ = 0.9995
AURORA_MULTI_AZ = 0.9999
CACHE_MULTI_AZ = 0.9999
EXTERNAL_DEFAULT = 0.999
_PERCENT = re.compile(r"(\d{2}(?:\.\d+)?)\s*%")


def series(*availabilities: float) -> float:
    result = 1.0
    for a in availabilities:
        result *= a
    return result


def parallel(availability: float, copies: int) -> float:
    return 1 - (1 - availability) ** max(copies, 1)


def component_availability(c: Component) -> float:
    if c.type in MANAGED_MULTI_AZ:
        return MANAGED_MULTI_AZ[c.type]
    if c.type is ComponentType.EXTERNAL_SERVICE:
        found = _PERCENT.search(c.notes or "")
        return float(found.group(1)) / 100 if found else EXTERNAL_DEFAULT
    multi_az = c.availability_zones > 1
    if c.type is ComponentType.RELATIONAL_DATABASE:
        if not multi_az:
            return SINGLE_INSTANCE
        return AURORA_MULTI_AZ if "aurora" in (c.aws_service or "").lower() else DATABASE_MULTI_AZ
    if c.type is ComponentType.CACHE:
        return CACHE_MULTI_AZ if multi_az else SINGLE_INSTANCE
    # compute (VM / containers / search / other): independent copies across AZs
    copies = c.autoscaling.min_replicas if c.autoscaling else c.replicas
    independent = min(copies, c.availability_zones)
    return parallel(SINGLE_INSTANCE, independent)


def request_path(graph: ComponentGraph) -> list[str]:
    """Components reachable from clients through synchronous edges (the critical path)."""
    entry = [c.id for c in graph.components if c.type is ComponentType.CLIENT]
    if not entry:  # no client modelled: every non-client component counts
        return [c.id for c in graph.components]
    seen: list[str] = []
    frontier = list(entry)
    while frontier:
        node = frontier.pop(0)
        for e in graph.edges_from(node):
            if e.mode is EdgeMode.SYNC and e.target not in seen:
                seen.append(e.target)
                frontier.append(e.target)
    return seen


def estimate_availability(graph: ComponentGraph, slo_percent: float | None) -> AvailabilityEstimate:
    path = [graph.component(i) for i in request_path(graph)]
    path = [c for c in path if c.type is not ComponentType.CLIENT]
    per = {c.id: component_availability(c) for c in path}
    total = series(*per.values()) if per else 1.0
    weakest = min(per, key=per.get) if per else None
    estimated = round(total * 100, 4)
    return AvailabilityEstimate(
        estimated_percent=estimated,
        slo_percent=slo_percent,
        meets_slo=None if slo_percent is None else estimated >= slo_percent,
        per_component_percent={k: round(v * 100, 4) for k, v in per.items()},
        weakest_component_id=weakest,
    )
