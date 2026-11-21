"""Evaluation cases: a design (YAML) + its answer key (JSON) with the same file stem.

Answer key format (`expected_findings/<case_id>.json`):
- acceptable_verdicts: verdicts we count as correct
- planted_flaws:     flaws the review MUST find (counted for recall)
- secondary_issues:  real but unplanted issues; finding them is fine, not required
- behaviours:        extra checks, e.g. the guard flags injection

A finding matches a flaw when its pillar is one of the flaw's pillars AND it names at least
one of the flaw's components (or the flaw is system-wide: no component ids).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from archoptimize.design_parsing.yaml_design_parser import load_design_file
from archoptimize.schemas import DesignSubmission, Pillar, Verdict

EVALUATION_DIR = Path(__file__).resolve().parent
TEST_DESIGNS_DIR = EVALUATION_DIR / "test_designs"
EXPECTED_FINDINGS_DIR = EVALUATION_DIR / "expected_findings"


class BehaviourCheck(StrEnum):
    INPUT_FLAGGED = "input_flagged"
    REQUIREMENT_CONFLICT_STATED = "requirement_conflict_stated"
    ASSUMPTIONS_LISTED = "assumptions_listed"


class ExpectedIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    pillars: list[Pillar] = Field(min_length=1)
    component_ids: list[str] = Field(default_factory=list)  # empty = system-wide


class ExpectedOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    summary: str
    acceptable_verdicts: list[Verdict] = Field(min_length=1)
    planted_flaws: list[ExpectedIssue] = Field(default_factory=list)
    secondary_issues: list[ExpectedIssue] = Field(default_factory=list)
    behaviours: list[BehaviourCheck] = Field(default_factory=list)


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    submission: DesignSubmission
    expected: ExpectedOutcome


class EvalCaseError(ValueError):
    pass


def _check_consistency(case_id: str, submission: DesignSubmission, expected: ExpectedOutcome):
    if expected.case_id != case_id:
        raise EvalCaseError(f"{case_id}: answer key says case_id '{expected.case_id}'")
    known = {c.id for c in submission.design.components}
    for issue in expected.planted_flaws + expected.secondary_issues:
        unknown = set(issue.component_ids) - known
        if unknown:
            raise EvalCaseError(f"{case_id}/{issue.id}: unknown components {sorted(unknown)}")


def load_cases(
    only: str | None = None,
    designs_dir: Path = TEST_DESIGNS_DIR,
    expected_dir: Path = EXPECTED_FINDINGS_DIR,
) -> list[EvalCase]:
    """Load every case (sorted by file name). `only` keeps cases whose id contains it."""
    cases: list[EvalCase] = []
    for design_path in sorted(designs_dir.glob("*.yaml")):
        case_id = design_path.stem
        if only and only not in case_id:
            continue
        expected_path = expected_dir / f"{case_id}.json"
        if not expected_path.exists():
            raise EvalCaseError(f"{case_id}: missing answer key {expected_path.name}")
        submission = load_design_file(design_path)
        expected = ExpectedOutcome.model_validate_json(expected_path.read_text(encoding="utf-8"))
        _check_consistency(case_id, submission, expected)
        cases.append(EvalCase(case_id, submission, expected))
    return cases
