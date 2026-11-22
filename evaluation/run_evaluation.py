"""Run a reviewer over every evaluation case, print a score table, save JSON results.

    uv run python -m evaluation.run_evaluation                       # default: rubber_stamp
    uv run python -m evaluation.run_evaluation --reviewer rubber_stamp --case pci
    uv run python -m evaluation.run_evaluation --no-save

Results go to evaluation/results/<timestamp>_<reviewer>.json (gitignored); copy the summary
line into the README / PLAN.md results table when a step changes quality.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from archoptimize.core.secret_redaction import redact
from archoptimize.schemas import DesignSubmission, ReviewResult
from evaluation.eval_cases import EVALUATION_DIR, load_cases
from evaluation.reference_reviewers import rubber_stamp
from evaluation.scoring import CaseScore, EvalSummary, score_case, summarize

Reviewer = Callable[[DesignSubmission], ReviewResult]


def _baseline(submission: DesignSubmission) -> ReviewResult:
    # imported lazily so the eval can run (rubber_stamp) without LLM libraries loaded
    from archoptimize.agents.baseline_reviewer import review_baseline

    return review_baseline(submission)


def _baseline_rag(submission: DesignSubmission) -> ReviewResult:
    from archoptimize.agents.baseline_reviewer import review_baseline
    from archoptimize.retrieval.pillar_retriever import default_retriever

    return review_baseline(submission, retriever=default_retriever())


def _board(submission: DesignSubmission, redesign: bool = False) -> ReviewResult:
    from archoptimize.retrieval.pillar_retriever import default_retriever
    from archoptimize.review_workflow.workflow_runner import run_review

    return run_review(submission, retriever=default_retriever(), redesign=redesign)


REVIEWERS: dict[str, Reviewer] = {
    "rubber_stamp": rubber_stamp,
    "baseline": _baseline,
    "baseline_rag": _baseline_rag,
    "board": _board,  # Step 5: multi-agent review only
    "board_redesign": lambda s: _board(s, redesign=True),  # Step 6: + Architect/Critic loop
}

RESULTS_DIR = EVALUATION_DIR / "results"


def run_evaluation(
    reviewer_name: str,
    reviewer: Reviewer,
    only: str | None = None,
    repeats: int = 1,
) -> tuple[EvalSummary, list[CaseScore]]:
    """Run every case `repeats` times. LLM answers vary between runs, so averaging over
    repeats gives a fairer comparison between steps (the summary covers all runs)."""
    scores: list[CaseScore] = []
    for _ in range(max(1, repeats)):
        for case in load_cases(only=only):
            started = time.perf_counter()
            try:
                result, error = reviewer(case.submission), None
            except Exception as exc:  # one broken case must not stop the whole run
                result, error = None, redact(f"{type(exc).__name__}: {exc}")[:300]
            scores.append(score_case(case, result, time.perf_counter() - started, error))
    return summarize(reviewer_name, scores), scores


def save_results(
    summary: EvalSummary, scores: list[CaseScore], results_dir: Path = RESULTS_DIR
) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = results_dir / f"{stamp}_{summary.reviewer}.json"
    payload = {
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary.as_dict(),
        "cases": [vars(s) for s in scores],
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def format_table(summary: EvalSummary, scores: list[CaseScore]) -> str:
    lines = [f"{'case':<32} {'flaws':>7} {'false':>6} {'verdict':<22} {'ok':<3} behaviours"]
    for s in scores:
        behaviours = " ".join(f"{k}={'✓' if v else '✗'}" for k, v in s.behaviours.items())
        lines.append(
            f"{s.case_id:<32} {s.flaws_found:>3}/{s.flaws_planted:<3} {s.false_alarms:>6} "
            f"{(s.verdict or 'ERROR'):<22} {'✓' if s.verdict_correct else '✗':<3} {behaviours}"
            + (f"  [{s.error}]" if s.error else "")
        )
    b, c = summary.behaviour_pass_rate, summary.citation_rate
    lines += [
        "",
        f"reviewer={summary.reviewer}  cases={summary.cases}  "
        f"flaw recall={summary.flaw_recall:.0%} ({summary.flaws_found}/{summary.flaws_planted})  "
        f"false alarms={summary.false_alarms}  verdict accuracy={summary.verdict_accuracy:.0%}  "
        f"behaviours={'n/a' if b is None else f'{b:.0%}'}  "
        f"cited={'n/a' if c is None else f'{c:.0%}'}  "
        + (
            f"redesigned={summary.redesigned_cases} fix rate="
            f"{'n/a' if summary.fix_rate is None else f'{summary.fix_rate:.0%}'}  "
            if summary.redesigned_cases
            else ""
        )
        + f"avg latency={summary.avg_latency_seconds:.2f}s  "
        f"avg tokens={summary.avg_tokens if summary.avg_tokens is not None else 'n/a'}  "
        f"errors={summary.errors}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run_evaluation")
    parser.add_argument("--reviewer", default="rubber_stamp", choices=sorted(REVIEWERS))
    parser.add_argument("--case", help="only run cases whose id contains this text")
    parser.add_argument("--no-save", action="store_true", help="do not write a results file")
    parser.add_argument("--repeats", type=int, default=1, help="runs per case (averaged)")
    args = parser.parse_args(argv)

    summary, scores = run_evaluation(
        args.reviewer, REVIEWERS[args.reviewer], only=args.case, repeats=args.repeats
    )
    if not scores:
        print("No cases matched.", file=sys.stderr)
        return 1
    print(format_table(summary, scores))
    if not args.no_save:
        print(f"\nSaved: {save_results(summary, scores)}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
