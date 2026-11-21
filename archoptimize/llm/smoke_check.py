"""Live check of the provider layer (Step 0 "Done when").

Run:  uv run python -m archoptimize.llm.smoke_check
Needs GROQ_API_KEY (and OPENROUTER_API_KEY for the OpenRouter checks) in .env.
Prints model names and replies only. Never prints keys.
"""

from __future__ import annotations

import sys

from pydantic import BaseModel

from archoptimize.core.secret_redaction import redact
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_catalog import fetch_groq_models
from archoptimize.llm.model_router import get_router


class Ping(BaseModel):
    ok: bool
    word: str


def _section(title: str) -> None:
    print(f"\n=== {title} ===")


def main() -> int:
    keys = ProviderKeys.from_env()
    router = get_router()
    print(
        f"Groq key: {'set' if keys.groq else 'MISSING'} | "
        f"OpenRouter key: {'set' if keys.openrouter else 'missing (optional)'}"
    )
    failed = False

    _section("1. Groq text reply (role: reviewer)")
    try:
        llm = router.get_llm("reviewer", keys, only_provider="groq")
        reply = llm.invoke("Reply with exactly: groq ok")
        print(f"model: {llm.last_candidate.label}\nreply: {reply.content!r}")
    except Exception as exc:
        failed = True
        print("FAILED:", redact(str(exc)))

    _section("2. Groq structured output (role: architect)")
    try:
        llm = router.get_llm("architect", keys, only_provider="groq").with_structured_output(Ping)
        result = llm.invoke("Return ok=true and word='pong'.")
        print(f"model: {llm.last_candidate.label}\nparsed: {result!r}")
    except Exception as exc:
        failed = True
        print("FAILED:", redact(str(exc)))

    _section("3. OpenRouter text reply (dynamically chosen fallback model)")
    if not keys.openrouter:
        print("skipped: no OpenRouter key")
    else:
        try:
            llm = router.get_llm("reviewer", keys, only_provider="openrouter")
            print("candidates:", [c.model for c in llm.candidates])
            reply = llm.invoke("Reply with exactly: openrouter ok")
            print(f"model: {llm.last_candidate.label}\nreply: {reply.content!r}")
        except Exception as exc:
            failed = True
            print("FAILED:", redact(str(exc)))

    _section("4. Selected models for vision and critic (no call)")
    for role in ("vision", "critic"):
        try:
            cands = router.candidates_for(role, keys)
            print(f"{role}: {[c.label for c in cands] or 'none available'}")
        except Exception as exc:
            print(f"{role}: FAILED:", redact(str(exc)))

    _section("5. Live Groq model list (for reference)")
    if keys.groq:
        try:
            url = router.settings.groq.models_url
            models = fetch_groq_models(url, keys.groq.get_secret_value())
            for m in sorted(models, key=lambda m: m.id):
                print(f"  {m.id:<50} ctx={m.context_length}")
        except Exception as exc:
            print("FAILED:", redact(str(exc)))

    print("\nRESULT:", "FAILED" if failed else "OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
