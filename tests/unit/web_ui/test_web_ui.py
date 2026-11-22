"""UI handlers with the review workflow faked (no keys, no network)."""

from __future__ import annotations

import gradio as gr

from archoptimize.design_parsing.yaml_design_parser import design_template_text
from archoptimize.retrieval import pillar_retriever
from archoptimize.review_workflow import workflow_runner
from archoptimize.schemas import ReviewResult, Verdict
from archoptimize.web_ui import demo_mode, event_handlers
from archoptimize.web_ui.app_builder import build_app
from archoptimize.web_ui.session_limits import SessionLimiter
from evaluation.eval_cases import load_cases

GROQ = "gsk_" + "k" * 40


def test_app_builds():
    assert isinstance(build_app(), gr.Blocks)


def test_only_the_chosen_input_box_is_visible():
    yaml_box, text_box = event_handlers.input_visibility("Text")
    assert yaml_box["visible"] is False and text_box["visible"] is True
    yaml_box, text_box = event_handlers.input_visibility("YAML")
    assert yaml_box["visible"] is True and text_box["visible"] is False


def test_parse_yaml_and_round_trip_for_editing():
    status, parsed, diagram = event_handlers.parse_input("YAML", design_template_text(), "", "", "")
    assert status.startswith("✅") and "```mermaid" in diagram
    assert event_handlers.preview_yaml(parsed).startswith("```mermaid")  # editable YAML re-parses


def test_parse_errors_are_friendly():
    status, parsed, _ = event_handlers.parse_input(
        "YAML", "design: {name: x, components: []}", "", "", ""
    )
    assert status.startswith("❌") and "design.components" in status and parsed == ""


def test_text_mode_needs_a_key():
    status, _, _ = event_handlers.parse_input("Text", "", "A web server and a DB " * 3, "", "")
    assert "Groq API key" in status


def test_review_without_key_explains_how_to_continue():
    parsed = event_handlers.submission_to_yaml(load_cases(only="01_")[0].submission)
    first = next(event_handlers.run_review_stream(parsed, "", "", "s1"))
    assert "Groq API key" in first[0] and first[-1] is None


def test_review_streams_events_then_results(monkeypatch):
    def fake_run_review(submission, *, keys, retriever, on_event):
        assert keys.groq.get_secret_value() == GROQ
        on_event("Input guard: clean")
        on_event("Chair: verdict reject")
        return ReviewResult(verdict=Verdict.REJECT, summary="Bad.")

    monkeypatch.setattr(workflow_runner, "run_review", fake_run_review)
    monkeypatch.setattr(event_handlers, "limiter", SessionLimiter())
    # don't depend on whether this machine has built the (gitignored) docs index
    monkeypatch.setattr(pillar_retriever, "default_retriever", lambda: None)
    parsed = event_handlers.submission_to_yaml(load_cases(only="01_")[0].submission)
    updates = list(event_handlers.run_review_stream(parsed, GROQ, "", "s2"))
    assert "Input guard" in updates[0][0]
    final = updates[-1]
    assert "Done" in final[0] and "⛔ Reject" in final[1]
    with open(final[-1], encoding="utf-8") as f:
        report = f.read()
    assert GROQ not in report  # keys never end up in the report


def test_review_that_hangs_times_out(monkeypatch):
    import threading

    release = threading.Event()

    def stuck_review(submission, *, keys, retriever, on_event):
        release.wait(5)
        return ReviewResult(verdict=Verdict.APPROVE)

    monkeypatch.setattr(workflow_runner, "run_review", stuck_review)
    monkeypatch.setattr(event_handlers, "limiter", SessionLimiter())
    monkeypatch.setattr(event_handlers, "MAX_REVIEW_SECONDS", 0.5)
    monkeypatch.setattr(pillar_retriever, "default_retriever", lambda: None)
    parsed = event_handlers.submission_to_yaml(load_cases(only="01_")[0].submission)
    last = list(event_handlers.run_review_stream(parsed, GROQ, "", "s3"))[-1]
    release.set()
    assert "longer than" in last[0]
    assert event_handlers.limiter.try_start("s3")[0]  # the slot was released


def test_session_limits():
    now = [0.0]
    limiter = SessionLimiter(max_per_hour=2, max_concurrent=1, clock=lambda: now[0])
    assert limiter.try_start("a")[0]
    assert not limiter.try_start("b")[0]  # one running at a time
    limiter.finish("a")
    assert limiter.try_start("a")[0]
    limiter.finish("a")
    ok, why = limiter.try_start("a")
    assert not ok and "per hour" in why
    now[0] = 3601
    assert limiter.try_start("a")[0]


def test_demo_mode_loads_precomputed_reviews(tmp_path, monkeypatch):
    sub = load_cases(only="01_")[0].submission
    demo = demo_mode.DemoReview(
        title="Demo A", submission=sub, result=ReviewResult(verdict="reject")
    )
    (tmp_path / "a.json").write_text(demo.model_dump_json(), encoding="utf-8")
    demo_mode.load_demos.cache_clear()
    monkeypatch.setattr(demo_mode, "DEMO_DIR", tmp_path)
    monkeypatch.setattr(
        event_handlers, "load_demos", lambda: demo_mode.load_demos.__wrapped__(tmp_path)
    )
    assert event_handlers.demo_titles() == ["Demo A"]
    out = event_handlers.open_demo("Demo A")
    assert "Demo review loaded" in out[0] and "⛔ Reject" in out[4]
    assert event_handlers.open_demo("missing")[0] == "Pick a demo review."
