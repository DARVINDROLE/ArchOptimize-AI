"""MCP calculator server: tool functions directly, one REAL stdio round trip, and fallback."""

from __future__ import annotations

import pytest

from archoptimize.calculators.design_metrics import measure_design
from archoptimize.mcp_server import calculator_client
from archoptimize.mcp_server.calculator_server import (
    availability,
    get_price,
    instances_needed,
    measure_designs,
    monthly_cost,
)
from evaluation.eval_cases import load_cases

SUB = load_cases(only="01_single")[0].submission


def test_tool_functions():
    assert get_price("ec2", "m5.large")["hourly_usd"] == 0.096
    assert get_price("ec2", "x9.mega")["hourly_usd"] is None
    assert (
        monthly_cost([{"name": "a", "hourly_usd": 0.1, "quantity": 2}])["total_monthly_usd"]
        == 146.0
    )
    assert instances_needed(500, 300)["instances"] == 3
    assert availability([99.5, 99.5])["percent"] == pytest.approx(99.0025)
    assert availability([99.0], parallel_copies=2)["percent"] == pytest.approx(99.99)


def test_measure_designs_tool_matches_local_calculators():
    out = measure_designs(
        [SUB.design.model_dump(mode="json", by_alias=True)],
        SUB.requirements.model_dump(mode="json"),
    )
    local = measure_design(SUB.design, SUB.requirements).model_dump(mode="json")
    assert out == [local]


def test_real_mcp_round_trip(monkeypatch):
    """Starts the server as a subprocess over stdio (a few seconds)."""
    monkeypatch.setenv("ARCHOPTIMIZE_CALCULATORS", "mcp")
    metrics, record = calculator_client.measure_designs_via_mcp([SUB.design], SUB.requirements)
    assert record.via == "mcp", record
    assert metrics[0] == measure_design(SUB.design, SUB.requirements)


def test_falls_back_to_local_when_mcp_fails(monkeypatch):
    monkeypatch.setenv("ARCHOPTIMIZE_CALCULATORS", "mcp")

    async def broken(*_args, **_kwargs):
        raise RuntimeError("server did not start")

    monkeypatch.setattr(calculator_client, "_call_mcp", broken)
    metrics, record = calculator_client.measure_designs_via_mcp([SUB.design], SUB.requirements)
    assert record.via == "local fallback"
    assert metrics[0].availability.meets_slo is False
