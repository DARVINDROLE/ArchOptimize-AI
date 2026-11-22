"""Button callbacks. They only talk to design_parsing, review_workflow and reporting.

Keys arrive from the UI per call and live only in this request (BYOK, session-only): they
are never logged, stored in state files, or written to the report.
"""

from __future__ import annotations

import logging
import queue
import tempfile
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import yaml

from archoptimize.core.errors import DesignInputError
from archoptimize.core.secret_redaction import redact
from archoptimize.design_parsing.text_design_parser import parse_design_text
from archoptimize.design_parsing.yaml_design_parser import parse_design_yaml
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.reporting.markdown_report import (
    build_report,
    cost_section,
    design_section,
    findings_section,
    trace_section,
    verdict_section,
)
from archoptimize.reporting.mermaid_diagram import to_mermaid_markdown
from archoptimize.schemas import DesignSubmission, ReviewResult
from archoptimize.web_ui.demo_mode import load_demos
from archoptimize.web_ui.session_limits import SessionLimiter

log = logging.getLogger(__name__)
limiter = SessionLimiter()
EMPTY = ""
MAX_REVIEW_SECONDS = 600  # give up waiting after 10 minutes (the worker thread is a daemon)


def submission_to_yaml(submission: DesignSubmission) -> str:
    data = submission.model_dump(mode="json", exclude_none=True, by_alias=True)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)


def _keys(groq_key: str, openrouter_key: str) -> ProviderKeys:
    return ProviderKeys.from_values(groq_key or None, openrouter_key or None)


def _friendly(exc: Exception) -> str:
    if isinstance(exc, DesignInputError):
        return "❌ " + exc.user_message.replace("\n", "  \n")
    return f"❌ {type(exc).__name__}: {redact(str(exc))[:400]}"


# ---------------------------------------------------------------- 1. parse + confirm
def input_visibility(mode: str):
    """Show the YAML editor or the free-text box, depending on the chosen format."""
    import gradio as gr

    return gr.update(visible=mode == "YAML"), gr.update(visible=mode == "Text")


def parse_input(mode: str, yaml_text: str, free_text: str, groq_key: str, openrouter_key: str):
    """Returns (status, editable YAML, diagram)."""
    try:
        if mode == "YAML":
            submission = parse_design_yaml(yaml_text)
        else:
            keys = _keys(groq_key, openrouter_key)
            if keys.groq is None:
                return (
                    "❌ Free-text input needs a Groq API key (or use YAML / demo mode).",
                    EMPTY,
                    EMPTY,
                )
            submission = parse_design_text(free_text, keys=keys)
    except Exception as exc:
        return _friendly(exc), EMPTY, EMPTY
    assumptions = submission.design.assumptions
    status = (
        f"✅ Parsed **{submission.design.name}**: {len(submission.design.components)} components, "
        f"{len(submission.design.edges)} connections. Check the design below, edit the YAML if "
        "needed, then run the review."
    )
    if assumptions:
        status += "\n\n**Assumptions made while reading your text:**\n" + "\n".join(
            f"- {a}" for a in assumptions
        )
    missing = submission.requirements.missing_essentials()
    if missing:
        status += f"\n\n⚠️ Requirements not stated: {', '.join(missing)}."
    return status, submission_to_yaml(submission), to_mermaid_markdown(submission.design)


def preview_yaml(parsed_yaml: str) -> str:
    try:
        return to_mermaid_markdown(parse_design_yaml(parsed_yaml).design)
    except Exception as exc:
        return _friendly(exc)


# ---------------------------------------------------------------- 2. review (streamed)
def _render(
    submission: DesignSubmission, result: ReviewResult
) -> tuple[str, str, str, str, str, str]:
    report = build_report(submission, result)
    path = Path(tempfile.gettempdir()) / f"archoptimize-review-{int(time.time())}.md"
    path.write_text(report, encoding="utf-8")
    return (
        verdict_section(result),
        findings_section(result),
        design_section(submission, result),
        cost_section(result),
        trace_section(result),
        str(path),
    )


def run_review_stream(
    parsed_yaml: str, groq_key: str, openrouter_key: str, session_id: str
) -> Iterator[tuple]:
    """Yields (progress, verdict, findings, design, cost, trace, report_file)."""
    blank = (EMPTY,) * 5 + (None,)
    try:
        submission = parse_design_yaml(parsed_yaml)
    except Exception as exc:
        yield (_friendly(exc), *blank)
        return
    keys = _keys(groq_key, openrouter_key)
    if keys.groq is None:
        yield ("❌ Paste a Groq API key to run a review (free at console.groq.com), "
               "or open a demo review.", *blank)  # fmt: skip
        return
    allowed, why = limiter.try_start(session_id)
    if not allowed:
        yield (f"⏳ {why}", *blank)
        return

    events: queue.Queue = queue.Queue()
    outcome: dict = {}

    def work() -> None:
        try:
            from archoptimize.retrieval.pillar_retriever import default_retriever
            from archoptimize.review_workflow.workflow_runner import run_review

            try:
                retriever = default_retriever()
            except Exception as exc:  # index missing: review still runs, uncited
                retriever = None
                events.put(f"⚠️ Documentation index unavailable ({exc}); findings will be uncited.")
            outcome["result"] = run_review(
                submission, keys=keys, retriever=retriever, on_event=events.put
            )
        except Exception as exc:
            outcome["error"] = exc
        finally:
            events.put(None)

    started = time.perf_counter()
    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    log_lines: list[str] = []
    try:
        while True:
            remaining = MAX_REVIEW_SECONDS - (time.perf_counter() - started)
            try:
                event = events.get(timeout=max(remaining, 0.1))
            except queue.Empty:
                timeout_msg = (
                    f"⏱️ The review took longer than {MAX_REVIEW_SECONDS // 60} minutes "
                    "(free-tier rate limits?). Please try again in a few minutes."
                )
                yield ("\n\n".join([*log_lines, timeout_msg]), *blank)
                return
            if event is None:
                break
            log_lines.append(f"`{time.perf_counter() - started:5.1f}s` {event}")
            yield ("\n\n".join(log_lines), *blank)
    finally:
        limiter.finish(session_id)
    if "error" in outcome:
        log.warning("review failed: %s", redact(str(outcome["error"]))[:300])
        yield ("\n\n".join([*log_lines, _friendly(outcome["error"])]), *blank)
        return
    log_lines.append(f"**Done in {time.perf_counter() - started:.0f}s.** See the result tabs.")
    yield ("\n\n".join(log_lines), *_render(submission, outcome["result"]))


# ---------------------------------------------------------------- 3. demo mode
def demo_titles() -> list[str]:
    return list(load_demos().keys())


def open_demo(title: str):
    """Returns (status, yaml, diagram, progress, verdict, findings, design, cost, trace, file)."""
    demo = load_demos().get(title)
    if demo is None:
        return ("Pick a demo review.", EMPTY, EMPTY, EMPTY, *(EMPTY,) * 5, None)
    rendered = _render(demo.submission, demo.result)
    return (
        f"📂 Demo review loaded: **{demo.submission.design.name}** (precomputed, no key needed).",
        submission_to_yaml(demo.submission),
        to_mermaid_markdown(demo.submission.design),
        "Demo mode: this review was computed earlier with the same multi-agent workflow.",
        *rendered,
    )
