"""Entry point for hosting (Render) and local runs:  uv run python app.py

On a host, PORT is set by the platform and the app must listen on 0.0.0.0.
Locally it defaults to http://127.0.0.1:7860.
"""

import logging
import os

from archoptimize.web_ui import build_app

logging.basicConfig(level=logging.WARNING)

app = build_app()

if __name__ == "__main__":
    port = os.getenv("PORT")
    app.queue(default_concurrency_limit=2).launch(
        server_name="0.0.0.0" if port else "127.0.0.1",
        server_port=int(port) if port else 7860,
    )
