"""Entry point for Hugging Face Spaces (and local runs):  uv run python app.py"""

import logging

from archoptimize.web_ui import build_app

logging.basicConfig(level=logging.WARNING)

app = build_app()

if __name__ == "__main__":
    app.queue(default_concurrency_limit=4).launch()
