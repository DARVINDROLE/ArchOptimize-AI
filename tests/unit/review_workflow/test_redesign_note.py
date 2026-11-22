"""Why is there (no) revised design? Reported while testing the live site: a rejected design
showed 'No redesign needed'."""

from __future__ import annotations

from archoptimize.reporting.markdown_report import design_section
from archoptimize.review_workflow.workflow_nodes import redesign_note
from archoptimize.schemas import ReviewResult, Verdict
from evaluation.eval_cases import load_cases

SUB = load_cases(only="01_")[0].submission


def state(verdict, **extra):
    return {"result": ReviewResult(verdict=verdict, **extra.pop("result_extra", {})), **extra}


def test_approved():
    assert "No redesign needed" in redesign_note(state(Verdict.APPROVE), True)


def test_rejected_for_missing_information_is_not_called_not_needed():
    note = redesign_note(state(Verdict.REJECT), True)
    assert "missing information" in note and "not needed" not in note.lower()


def test_rejected_for_conflicting_requirements():
    s = state(Verdict.REJECT, result_extra={"requirement_conflicts": ["99.999 % for $100"]})
    assert "requirements conflict" in redesign_note(s, True)


def test_architect_failure_is_explained():
    s = state(
        Verdict.REJECT,
        redesign_round=1,
        warnings=["Architect failed: AllModelsFailedError: rate limited"],
    )
    note = redesign_note(s, True)
    assert "could not be completed" in note and "rate limited" in note


def test_redesign_switched_off():
    assert "switched off" in redesign_note(state(Verdict.REJECT), False)


def test_page_never_says_not_needed_for_a_rejected_design():
    rejected = ReviewResult(verdict=Verdict.REJECT, redesign_note="")
    assert "not needed" not in design_section(SUB, rejected).lower()
    approved = ReviewResult(verdict=Verdict.APPROVE)
    assert "No redesign needed" in design_section(SUB, approved)
