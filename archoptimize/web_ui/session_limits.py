"""Protect the free Space (and the user's free-tier quota) from runaway use.

- at most MAX_PER_HOUR reviews per browser session per hour
- at most MAX_CONCURRENT reviews running at once on the whole Space
State is in memory only (the Space disk is ephemeral and we keep no history on it).
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

MAX_PER_HOUR = 6
MAX_CONCURRENT = 2
WINDOW_SECONDS = 3600


class SessionLimiter:
    def __init__(
        self,
        max_per_hour: int = MAX_PER_HOUR,
        max_concurrent: int = MAX_CONCURRENT,
        clock=time.monotonic,
    ):
        self._max_per_hour = max_per_hour
        self._max_concurrent = max_concurrent
        self._clock = clock
        self._starts: dict[str, deque] = defaultdict(deque)
        self._running = 0
        self._lock = threading.Lock()

    def try_start(self, session_id: str) -> tuple[bool, str]:
        now = self._clock()
        with self._lock:
            starts = self._starts[session_id]
            while starts and now - starts[0] > WINDOW_SECONDS:
                starts.popleft()
            if len(starts) >= self._max_per_hour:
                wait = int(WINDOW_SECONDS - (now - starts[0])) // 60 + 1
                limit = self._max_per_hour
                return False, f"Limit of {limit} reviews per hour reached; retry in ~{wait} min."
            if self._running >= self._max_concurrent:
                return False, "The Space is busy with other reviews; please try again in a minute."
            starts.append(now)
            self._running += 1
            return True, ""

    def finish(self, _session_id: str) -> None:
        with self._lock:
            self._running = max(0, self._running - 1)
