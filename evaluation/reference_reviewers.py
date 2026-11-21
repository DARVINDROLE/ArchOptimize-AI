"""Trivial reviewers that set the floor every real reviewer must beat.

`rubber_stamp` approves everything and finds nothing: the score of "no review at all".
"""

from __future__ import annotations

from archoptimize.schemas import DesignSubmission, ReviewResult, Verdict


def rubber_stamp(_submission: DesignSubmission) -> ReviewResult:
    return ReviewResult(verdict=Verdict.APPROVE, summary="Approved without review.")
