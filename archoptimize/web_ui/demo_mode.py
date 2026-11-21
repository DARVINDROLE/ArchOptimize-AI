"""Demo mode: precomputed reviews that visitors can open without an API key.

Build (uses your keys from .env, a few minutes):
    uv run python -m archoptimize.web_ui.demo_mode --cases 01_single 02_pci 04_well 15_over
"""

from __future__ import annotations

import argparse
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

from archoptimize.schemas import DesignSubmission, ReviewResult

DEMO_DIR = Path(__file__).resolve().parents[2] / "data" / "demo_reviews"


class DemoReview(BaseModel):
    title: str
    submission: DesignSubmission
    result: ReviewResult


@lru_cache(maxsize=1)
def load_demos(demo_dir: Path = DEMO_DIR) -> dict[str, DemoReview]:
    demos: dict[str, DemoReview] = {}
    for path in sorted(demo_dir.glob("*.json")):
        demo = DemoReview.model_validate_json(path.read_text(encoding="utf-8"))
        demos[demo.title] = demo
    return demos


def build_demos(case_filters: list[str], demo_dir: Path = DEMO_DIR) -> list[Path]:
    from archoptimize.retrieval.pillar_retriever import default_retriever
    from archoptimize.review_workflow.workflow_runner import run_review
    from evaluation.eval_cases import load_cases

    demo_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name in case_filters:
        for case in load_cases(only=name):
            print(f"Reviewing {case.case_id} ...", flush=True)
            result = run_review(case.submission, retriever=default_retriever(), on_event=print)
            demo = DemoReview(
                title=f"{case.submission.design.name} — {case.expected.summary}",
                submission=case.submission,
                result=result,
            )
            path = demo_dir / f"{case.case_id}.json"
            path.write_text(demo.model_dump_json(indent=1), encoding="utf-8")
            written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="demo_mode")
    parser.add_argument("--cases", nargs="+", required=True, help="eval case id filters")
    args = parser.parse_args(argv)
    for path in build_demos(args.cases):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
