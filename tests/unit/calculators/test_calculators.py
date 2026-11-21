"""Calculator tests: hand-checked math, plus the eval designs give the expected verdicts."""

from __future__ import annotations

import pytest

from archoptimize.calculators.availability import (
    component_availability,
    parallel,
    series,
)
from archoptimize.calculators.capacity import instance_vcpus, instances_needed
from archoptimize.calculators.design_metrics import measure_design
from archoptimize.calculators.price_source import JsonPriceSource
from archoptimize.schemas import Component, ComponentType
from evaluation.eval_cases import load_cases


def submission(name):
    return load_cases(only=name)[0].submission


def metrics(name):
    s = submission(name)
    return measure_design(s.design, s.requirements)


# --- availability -----------------------------------------------------------------------


def test_series_and_parallel_math():
    assert series(0.99, 0.99) == pytest.approx(0.9801)
    assert parallel(0.99, 2) == pytest.approx(0.9999)
    assert parallel(0.99, 0) == pytest.approx(0.99)  # at least one copy


def test_single_az_database_vs_multi_az():
    single = Component(id="db", name="DB", type=ComponentType.RELATIONAL_DATABASE)
    multi = single.model_copy(update={"availability_zones": 2})
    aurora = multi.model_copy(update={"aws_service": "Aurora PostgreSQL"})
    assert component_availability(single) == 0.995
    assert component_availability(multi) == 0.9995
    assert component_availability(aurora) == 0.9999


def test_copies_in_one_az_do_not_count_as_independent():
    same_az = Component(id="w", name="W", type=ComponentType.COMPUTE_VM, replicas=3)
    spread = same_az.model_copy(update={"availability_zones": 3})
    assert component_availability(same_az) == 0.995
    assert component_availability(spread) > 0.99999


def test_monolith_misses_its_slo():
    a = metrics("01_single_az_monolith").availability
    assert a.estimated_percent == pytest.approx(99.0025, abs=1e-3)  # 0.995 × 0.995
    assert a.meets_slo is False


def test_well_architected_design_meets_its_slo():
    a = metrics("04_well_architected").availability
    assert a.meets_slo is True
    assert "email-queue" not in a.per_component_percent  # async consumer is off the path


def test_sync_chain_is_capped_by_the_external_dependency():
    a = metrics("09_sync_call_chain").availability
    assert a.per_component_percent["fraud"] == 99.5  # parsed from its notes
    assert a.weakest_component_id == "fraud" and a.meets_slo is False


# --- capacity ---------------------------------------------------------------------------


def test_instance_sizes_and_instances_needed():
    assert instance_vcpus("m5.2xlarge") == 8
    assert instance_vcpus("t3.small") == pytest.approx(0.8)  # burstable
    assert instances_needed(500, 300) == 3  # 500 × 1.3 / 300 → 2.17 → 3
    with pytest.raises(ValueError):
        instances_needed(100, 0)


def test_undersized_gateway_cannot_serve_its_peak():
    c = metrics("06_impossible_requirements").capacity
    assert c.bottleneck_component_id == "gateway" and c.meets_peak is False


# --- cost -------------------------------------------------------------------------------


def test_overprovisioned_blog_blows_its_budget():
    cost = metrics("15_overprovisioned").cost
    assert cost.total_monthly_usd > 5 * 200
    assert cost.within_budget is False


def test_budget_conflict_case_is_far_over_budget():
    cost = metrics("03_budget_conflict").cost
    assert cost.total_monthly_usd > 10 * 500
    assert cost.peak_monthly_usd > cost.total_monthly_usd  # autoscaling to 40 nodes


def test_multi_az_rds_pays_for_a_standby():
    s = submission("10_no_backups")
    line = next(
        line
        for line in measure_design(s.design, s.requirements).cost.lines
        if line.component_id == "bookings-db"
    )
    assert line.monthly_usd == pytest.approx(2 * 0.171 * 730, rel=1e-3)


def test_unknown_instance_types_are_reported_not_guessed():
    s = submission("01_single_az_monolith")
    design = s.design.model_copy(
        update={
            "components": [
                c.model_copy(update={"instance_type": "x9.mega"}) if c.id == "web" else c
                for c in s.design.components
            ]
        }
    )
    assert measure_design(design, s.requirements).cost.unpriced_component_ids == ["web"]


def test_other_regions_cost_more():
    prices = JsonPriceSource()
    assert prices.hourly("ec2", "m5.large", "eu-west-1") > prices.hourly("ec2", "m5.large")


def test_headline_mentions_all_numbers():
    line = metrics("01_single_az_monolith").headline()
    assert "cost" in line and "availability" in line and "capacity" in line
