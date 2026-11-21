"""Command-line entry point for local use.

uv run python -m archoptimize.cli preview path/to/design.yaml   # validate + print Mermaid
uv run python -m archoptimize.cli template                      # print the YAML template
"""

from __future__ import annotations

import argparse
import sys

from archoptimize.core.errors import DesignInputError
from archoptimize.design_parsing.yaml_design_parser import design_template_text, load_design_file
from archoptimize.reporting.mermaid_diagram import to_mermaid_markdown


def _preview(path: str) -> int:
    try:
        submission = load_design_file(path)
    except DesignInputError as err:
        print(err.user_message, file=sys.stderr)
        return 1
    except OSError as err:
        print(f"Cannot read {path}: {err.strerror}", file=sys.stderr)
        return 1

    design, req = submission.design, submission.requirements
    print(f"Design: {design.name} — {len(design.components)} components, {len(design.edges)} edges")
    missing = req.missing_essentials()
    if missing:
        print(f"Requirements not stated: {', '.join(missing)}")
    print()
    print(to_mermaid_markdown(design))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="archoptimize")
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview", help="validate a YAML design and print its diagram")
    preview.add_argument("path")
    sub.add_parser("template", help="print the YAML design template")
    args = parser.parse_args(argv)

    if args.command == "preview":
        return _preview(args.path)
    print(design_template_text())
    return 0


if __name__ == "__main__":
    # Windows consoles default to a legacy code page; force UTF-8 so '—', '×' etc. survive
    # printing and redirection (e.g. `template > design.yaml`).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main())
