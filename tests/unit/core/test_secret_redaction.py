from __future__ import annotations

import pytest

from archoptimize.core.secret_redaction import REDACTED, redact


@pytest.mark.parametrize(
    "secret",
    [
        "gsk_" + "b" * 30,  # Groq
        "sk-or-v1-" + "c" * 40,  # OpenRouter
        "hf_" + "d" * 30,  # Hugging Face
    ],
)
def test_redacts_known_key_shapes(secret):
    assert redact(f"error with {secret} inside") == f"error with {REDACTED} inside"


def test_leaves_normal_text_alone():
    assert redact("rate limit reached, retry in 5s") == "rate limit reached, retry in 5s"
