from __future__ import annotations

from archoptimize.llm.api_keys import ProviderKeys


def test_key_values_are_hidden_in_repr_and_str():
    keys = ProviderKeys.from_values(groq="gsk_" + "a" * 40)
    assert keys.groq is not None
    assert "gsk_" not in repr(keys)
    assert "gsk_" not in str(keys)


def test_placeholders_and_blank_values_are_ignored():
    keys = ProviderKeys.from_values(groq="  ", openrouter="sk-or-v1-your_key_here")
    assert keys.groq is None
    assert keys.openrouter is None
