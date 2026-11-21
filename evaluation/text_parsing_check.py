"""Step 8 check: the same design as YAML and as free text gives near-identical graphs.

uv run python -m evaluation.text_parsing_check        # uses Groq (normalizer role)
"""

from __future__ import annotations

import sys

from archoptimize.design_parsing.text_design_parser import parse_design_text
from evaluation.eval_cases import EVALUATION_DIR, load_cases
from evaluation.graph_similarity import graph_similarity

TEXT_DIR = EVALUATION_DIR / "text_designs"
PASS_SIMILARITY = 0.8


def main() -> int:
    scores = []
    for path in sorted(TEXT_DIR.glob("*.txt")):
        case = load_cases(only=path.stem)[0]
        parsed = parse_design_text(path.read_text(encoding="utf-8"))
        score = graph_similarity(case.submission.design, parsed.design)
        req_a, req_b = case.submission.requirements, parsed.requirements
        req_ok = (req_a.availability_slo_percent, req_a.peak_rps, req_a.monthly_budget_usd) == (
            req_b.availability_slo_percent,
            req_b.peak_rps,
            req_b.monthly_budget_usd,
        )
        scores.append(score)
        status = "PASS" if score >= PASS_SIMILARITY and req_ok else "FAIL"
        print(f"{status}  {path.stem:<28} similarity={score:.2f}  requirements_match={req_ok}")
        for a in parsed.design.assumptions[:3]:
            print(f"        assumption: {a}")
        if status == "FAIL":
            for c in parsed.design.components:
                print(
                    f"        parsed {c.id} {c.type.value} az={c.availability_zones} "
                    f"replicas={c.replicas} public={c.public}"
                )
            for e in parsed.design.edges:
                print(f"        parsed edge {e.source} -> {e.target}")
    ok = all(s >= PASS_SIMILARITY for s in scores)
    print(f"\naverage similarity {sum(scores) / len(scores):.2f} (pass ≥ {PASS_SIMILARITY})")
    return 0 if ok else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
