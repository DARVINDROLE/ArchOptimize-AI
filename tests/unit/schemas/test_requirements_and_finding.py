from __future__ import annotations

import pytest
from pydantic import ValidationError

from archoptimize.schemas import ComplianceStandard, Finding, Pillar, Requirements, Severity


def test_missing_essentials_lists_unstated_fields():
    req = Requirements(peak_rps=500)
    assert req.missing_essentials() == ["availability_slo_percent", "monthly_budget_usd"]


def test_compliance_lookup():
    req = Requirements(compliance=["pci_dss"])
    assert req.requires(ComplianceStandard.PCI_DSS)
    assert not req.requires(ComplianceStandard.HIPAA)


@pytest.mark.parametrize(
    "field, value",
    [
        ("availability_slo_percent", 100),  # 100 % is impossible
        ("availability_slo_percent", 0),
        ("peak_rps", 0),
        ("monthly_budget_usd", -1),
        ("region", "US East"),
        ("compliance", ["iso_42"]),
    ],
)
def test_invalid_requirements(field, value):
    with pytest.raises(ValidationError):
        Requirements(**{field: value})


def test_finding_and_severity_ranking():
    finding = Finding(
        id="REL-001",
        pillar=Pillar.RELIABILITY,
        severity=Severity.HIGH,
        title="Single-AZ database",
        component_ids=["orders-db"],
        evidence="orders-db runs in 1 AZ but the SLO is 99.9 %.",
        recommendation="Enable Multi-AZ.",
        citation_chunk_ids=["rel-chunk-12"],
    )
    assert finding.pillar is Pillar.RELIABILITY
    ordered = sorted(Severity, key=lambda s: s.rank, reverse=True)
    assert ordered[0] is Severity.CRITICAL and ordered[-1] is Severity.INFO


def test_finding_json_schema_has_descriptions_for_the_llm():
    schema = Finding.model_json_schema()
    assert "description" in schema["properties"]["evidence"]
