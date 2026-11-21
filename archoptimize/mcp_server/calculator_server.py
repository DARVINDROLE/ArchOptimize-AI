"""FastMCP server exposing the calculators as MCP tools (stdio transport).

Tools
- get_price(family, size, region)              hourly USD price from the snapshot
- monthly_cost(items)                          sum of {hourly_usd, quantity} lines per month
- instances_needed(peak_rps, per_instance_rps, headroom)
- availability(series_percents, parallel_copies)
- measure_designs(designs, requirements)       cost + availability + capacity per design
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from archoptimize.calculators.availability import parallel, series
from archoptimize.calculators.capacity import instances_needed as _instances_needed
from archoptimize.calculators.design_metrics import measure_design
from archoptimize.calculators.price_source import DEFAULT_REGION, default_price_source
from archoptimize.schemas import ComponentGraph, Requirements

mcp = FastMCP("archoptimize-calculators", log_level="WARNING")


@mcp.tool()
def get_price(family: str, size: str = "", region: str = DEFAULT_REGION) -> dict:
    """Hourly on-demand USD price, e.g. family='ec2', size='m5.large'. price=None if unknown."""
    prices = default_price_source()
    return {
        "family": family,
        "size": size,
        "region": region,
        "hourly_usd": prices.hourly(family, size or None, region),
        "basis": prices.describe(),
    }


@mcp.tool()
def monthly_cost(items: list[dict]) -> dict:
    """Monthly USD for items like [{"name": "web", "hourly_usd": 0.096, "quantity": 2}]."""
    hours = default_price_source().hours_per_month
    lines = [
        {
            "name": str(i.get("name", "")),
            "monthly_usd": round(float(i["hourly_usd"]) * float(i.get("quantity", 1)) * hours, 2),
        }
        for i in items
    ]
    return {"lines": lines, "total_monthly_usd": round(sum(x["monthly_usd"] for x in lines), 2)}


@mcp.tool()
def instances_needed(peak_rps: float, per_instance_rps: float, headroom: float = 0.3) -> dict:
    """Instances needed to serve peak_rps with spare headroom (0.3 = 30 %)."""
    return {"instances": _instances_needed(peak_rps, per_instance_rps, headroom)}


@mcp.tool()
def availability(series_percents: list[float], parallel_copies: int = 1) -> dict:
    """Availability of components in series (all needed); the chain is copied
    `parallel_copies` times independently (one copy is enough)."""
    chain = series(*(p / 100 for p in series_percents))
    return {"percent": round(parallel(chain, parallel_copies) * 100, 5)}


@mcp.tool()
def measure_designs(designs: list[dict], requirements: dict) -> list[dict]:
    """Cost, availability and capacity for each design (ComponentGraph JSON) against the
    requirements (Requirements JSON). Returns one DesignMetrics JSON per design."""
    req = Requirements.model_validate(requirements)
    return [
        measure_design(ComponentGraph.model_validate(d), req).model_dump(mode="json")
        for d in designs
    ]


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
