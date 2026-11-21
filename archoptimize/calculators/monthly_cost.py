"""Estimate the monthly cost of a design from its components (instance types × replicas ×
hours, plus request-priced services). Approximate by design: good for comparing options
and for spotting an order-of-magnitude budget problem."""

from __future__ import annotations

from archoptimize.calculators.price_source import PriceSource, default_price_source
from archoptimize.schemas import Component, ComponentGraph, ComponentType, Requirements
from archoptimize.schemas.design_metrics import CostEstimate, CostLine

# average traffic as a share of the stated peak (typical day/night pattern)
AVERAGE_TO_PEAK = 0.25
SECONDS_PER_MONTH = 2_628_000


def _monthly_requests(req: Requirements) -> float:
    return (req.peak_rps or 0) * AVERAGE_TO_PEAK * SECONDS_PER_MONTH


def _service_text(c: Component) -> str:
    return (c.aws_service or "").lower()


def _fleet(c: Component) -> tuple[int, int]:
    """(baseline copies, peak copies)."""
    if c.autoscaling:
        return c.autoscaling.min_replicas, c.autoscaling.max_replicas
    return c.replicas, c.replicas


def price_component(
    c: Component, req: Requirements, prices: PriceSource
) -> tuple[float, float, str] | None:
    """(baseline monthly, peak monthly, description) or None if unknown."""
    hours, region = prices.hours_per_month, req.region
    base_n, peak_n = _fleet(c)
    svc = _service_text(c)
    million_req = _monthly_requests(req) / 1_000_000

    def per_instance(family: str) -> float | None:
        h = prices.hourly(family, c.instance_type, region)
        return None if h is None else h * hours

    t = c.type
    if t is ComponentType.COMPUTE_VM:
        each = per_instance("ec2")
        if each is None:
            return None
        return each * base_n, each * peak_n, f"{base_n}-{peak_n} × EC2 {c.instance_type}"

    if t is ComponentType.CONTAINER_SERVICE:
        extra = (
            (prices.hourly("eks_control_plane", region=region) or 0) * hours if "eks" in svc else 0
        )
        each = per_instance("ec2") if c.instance_type else None
        if each is None:
            each = (prices.hourly("fargate_task_1vcpu_2gb", region=region) or 0) * hours
            kind = "Fargate tasks (1 vCPU / 2 GB)"
        else:
            kind = f"nodes {c.instance_type}"
        return each * base_n + extra, each * peak_n + extra, f"{base_n}-{peak_n} × {kind}"

    if t in (ComponentType.RELATIONAL_DATABASE, ComponentType.CACHE, ComponentType.SEARCH):
        family = {
            ComponentType.CACHE: "elasticache",
            ComponentType.SEARCH: "opensearch",
        }.get(t, "aurora" if "aurora" in svc else "rds")
        each = per_instance(family)
        if each is None:
            return None
        copies = c.replicas
        # RDS Multi-AZ keeps a standby copy: twice the instance cost
        if family == "rds" and c.availability_zones > 1:
            copies = max(copies, 2)
        return each * copies, each * copies, f"{copies} × {family} {c.instance_type}"

    if t is ComponentType.LOAD_BALANCER:
        cost = (prices.hourly("load_balancer", region=region) or 0) * hours
        return cost, cost, "load balancer (base + ~2 LCU)"

    if t is ComponentType.WAF:
        cost = (prices.monthly_fixed("waf_web_acl_with_10_rules", region) or 0) + million_req * (
            prices.per_million_requests("waf", region) or 0
        )
        return cost, cost, "WAF web ACL + requests"

    if t is ComponentType.CDN:
        cost = (prices.monthly_fixed("cloudfront_base", region) or 0) + million_req * (
            prices.per_million_requests("cloudfront", region) or 0
        )
        return cost, cost, "CloudFront base + requests"

    if t is ComponentType.DNS:
        cost = prices.monthly_fixed("route53_hosted_zone", region) or 0
        return cost, cost, "hosted zone"

    if t is ComponentType.OBJECT_STORAGE:
        cost = prices.monthly_fixed("s3_100gb_storage", region) or 0
        return cost, cost, "S3 ~100 GB"

    per_request_service = {
        ComponentType.API_GATEWAY: "api_gateway",
        ComponentType.SERVERLESS_FUNCTION: "lambda",
        ComponentType.NOSQL_DATABASE: "dynamodb_on_demand",
        ComponentType.QUEUE: "sqs",
    }.get(t)
    if per_request_service:
        cost = million_req * (prices.per_million_requests(per_request_service, region) or 0)
        return cost, cost, f"{per_request_service} on {million_req:,.0f}M requests/month"

    if t is ComponentType.STREAM:
        cost = (prices.hourly("kinesis_shard", region=region) or 0) * hours * c.replicas
        return cost, cost, f"{c.replicas} × Kinesis shard"

    return None  # client, external service, other: not priced


def estimate_monthly_cost(
    graph: ComponentGraph, req: Requirements, prices: PriceSource | None = None
) -> CostEstimate:
    prices = prices or default_price_source()
    lines, unpriced = [], []
    total = peak = 0.0
    for c in graph.components:
        if c.type in (ComponentType.CLIENT, ComponentType.EXTERNAL_SERVICE):
            continue
        priced = price_component(c, req, prices)
        if priced is None:
            unpriced.append(c.id)
            continue
        base, top, description = priced
        total += base
        peak += top
        lines.append(
            CostLine(component_id=c.id, description=description, monthly_usd=round(base, 2))
        )
    budget = req.monthly_budget_usd
    return CostEstimate(
        total_monthly_usd=round(total, 2),
        peak_monthly_usd=round(peak, 2),
        lines=lines,
        unpriced_component_ids=unpriced,
        budget_usd=budget,
        within_budget=None if budget is None else total <= budget,
        basis=prices.describe(),
    )
