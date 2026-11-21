from __future__ import annotations

import pytest

from archoptimize.agents.agent_base import PROMPTS_DIR, load_prompt, render_prompt


def test_render_fills_placeholders_and_ignores_json_braces():
    template = 'Review {design} and answer like {"verdict": "..."}'
    assert render_prompt(template, design="X") == 'Review X and answer like {"verdict": "..."}'


def test_render_rejects_missing_and_unused_values():
    with pytest.raises(KeyError, match="without a value"):
        render_prompt("{a} {b}", a="1")
    with pytest.raises(KeyError, match="not in the prompt"):
        render_prompt("{a}", a="1", b="2")


def test_every_prompt_file_loads():
    names = [p.stem for p in PROMPTS_DIR.glob("*.md")]
    assert "baseline_reviewer" in names
    for name in names:
        assert load_prompt(name).strip()
