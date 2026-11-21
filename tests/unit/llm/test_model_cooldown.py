from __future__ import annotations

from archoptimize.llm.model_cooldown import Cooldown


def test_cooldown_expires(fake_clock):
    cooldown = Cooldown(60, clock=fake_clock)
    cooldown.mark("some/model")
    assert cooldown.is_cooling("some/model")
    assert not cooldown.is_cooling("other/model")

    fake_clock.now = 61
    assert not cooldown.is_cooling("some/model")
