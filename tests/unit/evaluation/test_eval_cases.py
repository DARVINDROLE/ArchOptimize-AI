"""The evaluation set itself must be valid: every design parses, every answer key matches."""

from __future__ import annotations

import json

import pytest

from archoptimize.schemas import Verdict
from evaluation.eval_cases import (
    TEST_DESIGNS_DIR,
    BehaviourCheck,
    EvalCaseError,
    load_cases,
)


@pytest.fixture(scope="module")
def cases():
    return load_cases()


def test_has_12_to_15_cases_all_valid(cases):
    assert 12 <= len(cases) <= 15
    assert len({c.case_id for c in cases}) == len(cases)


def test_required_scenarios_are_present(cases):
    by_id = {c.case_id: c for c in cases}
    good = by_id["04_well_architected"].expected
    assert Verdict.APPROVE in good.acceptable_verdicts and not good.planted_flaws
    assert BehaviourCheck.INPUT_FLAGGED in by_id["05_prompt_injection"].expected.behaviours
    assert BehaviourCheck.REQUIREMENT_CONFLICT_STATED in (
        by_id["06_impossible_requirements"].expected.behaviours
    )
    assert BehaviourCheck.ASSUMPTIONS_LISTED in by_id["07_vague_design"].expected.behaviours
    assert by_id["02_pci_public_bucket"].expected.acceptable_verdicts == [Verdict.REJECT]


def test_every_flawed_case_plants_at_least_one_flaw(cases):
    without_flaws = {c.case_id for c in cases if not c.expected.planted_flaws}
    assert without_flaws == {"04_well_architected", "07_vague_design"}


def test_filter_by_name():
    assert [c.case_id for c in load_cases(only="pci")] == ["02_pci_public_bucket"]


def test_inconsistent_answer_key_is_rejected(tmp_path):
    designs, expected = tmp_path / "designs", tmp_path / "expected"
    designs.mkdir()
    expected.mkdir()
    (designs / "x.yaml").write_text(
        (TEST_DESIGNS_DIR / "13_public_database.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    key = {
        "case_id": "x",
        "summary": "s",
        "acceptable_verdicts": ["reject"],
        "planted_flaws": [
            {"id": "f", "description": "d", "pillars": ["security"], "component_ids": ["ghost"]}
        ],
    }
    (expected / "x.json").write_text(json.dumps(key), encoding="utf-8")
    with pytest.raises(EvalCaseError, match="unknown components"):
        load_cases(designs_dir=designs, expected_dir=expected)


def test_missing_answer_key_is_rejected(tmp_path):
    (tmp_path / "y.yaml").write_text(
        "design: {name: y, components: [{id: a, name: A, type: other}]}"
    )
    with pytest.raises(EvalCaseError, match="missing answer key"):
        load_cases(designs_dir=tmp_path, expected_dir=tmp_path)
