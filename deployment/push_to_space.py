"""Upload the app to its Hugging Face Space (creates the Space on first run).

    uv run python -m deployment.push_to_space --space Laukik7/ArchOptimize-AI

Needs HF_TOKEN (write access) in the environment or .env. Ships the app code, the prebuilt
documentation index (data/knowledge_index, built with the index_builder) and the demo
reviews. The index is large and kept out of git (D26); the HF upload API handles it.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
INCLUDE = [
    "app.py",
    "README.md",
    "LICENSE",
    "requirements.txt",
    "archoptimize/**",
    "data/knowledge_index/**",
    "data/demo_reviews/**",
]
EXCLUDE = ["**/__pycache__/**", "**/*.pyc"]


def check_ready() -> list[str]:
    problems = []
    if not (ROOT / "data" / "knowledge_index" / "chroma.sqlite3").exists():
        problems.append("index missing: run python -m archoptimize.knowledge_base.index_builder")
    if not list((ROOT / "data" / "demo_reviews").glob("*.json")):
        problems.append("no demo reviews: run python -m archoptimize.web_ui.demo_mode --cases ...")
    if not (ROOT / "requirements.txt").exists():
        problems.append("requirements.txt missing: run uv export (see README)")
    return problems


def main(argv: list[str] | None = None) -> int:
    from huggingface_hub import HfApi

    parser = argparse.ArgumentParser(prog="push_to_space")
    parser.add_argument("--space", required=True, help="e.g. Laukik7/ArchOptimize-AI")
    parser.add_argument("--message", default="Deploy ArchOptimize AI")
    args = parser.parse_args(argv)

    load_dotenv(ROOT / ".env")
    token = os.getenv("HF_TOKEN")
    if not token:
        print("HF_TOKEN is not set", file=sys.stderr)
        return 1
    problems = check_ready()
    if problems:
        print("Not ready to deploy:\n- " + "\n- ".join(problems), file=sys.stderr)
        return 1

    api = HfApi(token=token)
    api.create_repo(args.space, repo_type="space", space_sdk="gradio", exist_ok=True)
    commit = api.upload_folder(
        repo_id=args.space,
        repo_type="space",
        folder_path=str(ROOT),
        allow_patterns=INCLUDE,
        ignore_patterns=EXCLUDE,
        commit_message=args.message,
    )
    print(f"Uploaded: {commit.commit_url}")
    print(f"Space:    https://huggingface.co/spaces/{args.space}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
