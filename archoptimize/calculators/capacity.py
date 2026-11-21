"""Capacity: how many requests per second can the compute tier serve, and how many instances
are needed for the stated peak?

Rule of thumb used (documented, adjustable): ~150 RPS per vCPU for a typical web/API
workload; burstable t-family instances count at 40 % of their vCPUs; a Fargate task is
1 vCPU; Lambda is limited by its default concurrency (1,000) at ~100 ms per request.
"""

from __future__ import annotations

import math

from archoptimize.schemas import Component, ComponentGraph, ComponentType, Requirements
from archoptimize.schemas.design_metrics import CapacityCheck

RPS_PER_VCPU = 150
BURSTABLE_FACTOR = 0.4
LAMBDA_DEFAULT_CONCURRENCY = 1000
LAMBDA_SECONDS_PER_REQUEST = 0.1
DEFAULT_HEADROOM = 0.3

_SIZE_VCPUS = {
    "nano": 2, "micro": 2, "small": 2, "medium": 2, "large": 2, "xlarge": 4,
    "2xlarge": 8, "4xlarge": 16, "8xlarge": 32, "12xlarge": 48, "16xlarge": 64,
}  # fmt: skip


def instance_vcpus(instance_type: str | None) -> float:
    """Effective vCPUs of an instance type like 'm5.large' (unknown → 2)."""
    if not instance_type or "." not in instance_type:
        return 2.0
    family, size = instance_type.removeprefix("db.").removeprefix("cache.").split(".", 1)
    vcpus = float(_SIZE_VCPUS.get(size.split(".")[0], 2))
    return vcpus * (BURSTABLE_FACTOR if family.startswith("t") else 1.0)


def instances_needed(
    peak_rps: float, per_instance_rps: float, headroom: float = DEFAULT_HEADROOM
) -> int:
    """Instances to serve `peak_rps` with `headroom` spare (0.3 = 30 %)."""
    if per_instance_rps <= 0:
        raise ValueError("per_instance_rps must be positive")
    return max(1, math.ceil(peak_rps * (1 + headroom) / per_instance_rps))


def component_capacity_rps(c: Component) -> float | None:
    """Max RPS of a compute component at its largest fleet size; None for non-compute."""
    copies = c.autoscaling.max_replicas if c.autoscaling else c.replicas
    if c.type is ComponentType.COMPUTE_VM:
        return copies * instance_vcpus(c.instance_type) * RPS_PER_VCPU
    if c.type is ComponentType.CONTAINER_SERVICE:
        per = instance_vcpus(c.instance_type) if c.instance_type else 1.0
        return copies * per * RPS_PER_VCPU
    if c.type is ComponentType.SERVERLESS_FUNCTION:
        return LAMBDA_DEFAULT_CONCURRENCY / LAMBDA_SECONDS_PER_REQUEST
    return None


def check_capacity(graph: ComponentGraph, req: Requirements) -> CapacityCheck:
    capacities = {
        c.id: round(cap, 1)
        for c in graph.components
        if (cap := component_capacity_rps(c)) is not None
    }
    if not capacities:
        return CapacityCheck(
            peak_rps=req.peak_rps,
            bottleneck_component_id=None,
            capacity_rps=None,
            meets_peak=None,
            per_component_rps={},
        )
    bottleneck = min(capacities, key=capacities.get)
    capacity = capacities[bottleneck]
    return CapacityCheck(
        peak_rps=req.peak_rps,
        bottleneck_component_id=bottleneck,
        capacity_rps=capacity,
        meets_peak=None if req.peak_rps is None else capacity >= req.peak_rps,
        per_component_rps=capacities,
    )
