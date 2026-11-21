"""Input guard: detect prompt-injection attempts in the user's design before review.

Two layers:
1. rules  — regexes for well-known injection phrases (always run, free, no network)
2. model  — Llama Prompt Guard 2 on Groq: returns the probability that a text is an
            injection. It reads at most ~512 tokens, so long text is checked in chunks.
The review still runs when input is flagged (the design may contain real flaws); the result
is marked so reviewers and the UI know. All text fields of the design are scanned.
"""

from __future__ import annotations

import logging
import re

from archoptimize.core.secret_redaction import redact
from archoptimize.llm.api_keys import ProviderKeys
from archoptimize.llm.model_router import ModelRouter, get_router
from archoptimize.schemas import DesignSubmission, GuardResult

log = logging.getLogger(__name__)

ROLE = "guard"
FLAG_THRESHOLD = 0.5
CHUNK_CHARS = 1500  # ~400 tokens, under the model's 512-token window

_INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |the )?(previous|prior|above)",
    r"(you must|you have to|always) (answer|respond|reply|say|approve)",
    r"\bapprove this design\b",
    r"system (prompt|note|message) to the (ai|model|reviewer)",
    r"\b(reveal|print|show) (your|the) (system )?prompt\b",
]
_PATTERN = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)


def collect_free_text(submission: DesignSubmission) -> str:
    """Every user-written text field, one per line."""
    d = submission.design
    texts = [d.name, d.description, *d.assumptions]
    for c in d.components:
        texts += [c.name, c.aws_service or "", c.instance_type or "", c.notes]
    texts += [e.description for e in d.edges] + [e.protocol or "" for e in d.edges]
    return "\n".join(t for t in texts if t)


def rule_matches(text: str) -> list[str]:
    return sorted({m.group(0).lower() for m in _PATTERN.finditer(text)})


def _chunks(text: str) -> list[str]:
    return [text[i : i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)] or [""]


def check_input(
    submission: DesignSubmission,
    *,
    keys: ProviderKeys | None = None,
    router: ModelRouter | None = None,
    use_model: bool = True,
) -> GuardResult:
    text = collect_free_text(submission)
    reasons = [f'phrase "{m}"' for m in rule_matches(text)]
    max_score, model = (1.0 if reasons else 0.0), None

    if use_model and text.strip():
        try:
            llm = (router or get_router()).get_llm(ROLE, keys or ProviderKeys.from_env())
            for chunk in _chunks(text):
                score = float(str(llm.invoke(chunk).content).strip())
                model = llm.last_candidate.label if llm.last_candidate else None
                if score >= FLAG_THRESHOLD:
                    reasons.append(f"prompt-guard score {score:.2f}")
                max_score = max(max_score, score)
        except Exception as exc:  # the model is an extra layer; rules still apply
            log.warning("prompt-guard unavailable: %s", redact(str(exc))[:200])

    return GuardResult(
        flagged=bool(reasons), max_score=min(max_score, 1.0), reasons=reasons, model=model
    )
