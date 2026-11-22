"""The behaviour CI revealed, now tested on purpose: without the docs index the review still
runs, and the user is told that findings will be uncited."""

from __future__ import annotations

from archoptimize.retrieval import pillar_retriever
from archoptimize.review_workflow import workflow_runner
from archoptimize.schemas import ReviewResult, Verdict
from archoptimize.web_ui import event_handlers
from archoptimize.web_ui.session_limits import SessionLimiter
from evaluation.eval_cases import load_cases


def test_missing_index_warns_and_review_still_runs(monkeypatch):
    def no_index():
        raise pillar_retriever.IndexNotBuiltError("The documentation index is empty.")

    seen = {}

    def fake_run_review(submission, *, keys, retriever, on_event):
        seen["retriever"] = retriever
        return ReviewResult(verdict=Verdict.APPROVE)

    monkeypatch.setattr(pillar_retriever, "default_retriever", no_index)
    monkeypatch.setattr(workflow_runner, "run_review", fake_run_review)
    monkeypatch.setattr(event_handlers, "limiter", SessionLimiter())
    parsed = event_handlers.submission_to_yaml(load_cases(only="01_")[0].submission)
    updates = list(event_handlers.run_review_stream(parsed, "gsk_" + "k" * 40, "", "s9"))

    assert "Documentation index unavailable" in updates[0][0]
    assert seen["retriever"] is None
    assert "✅ Approve" in updates[-1][1]
