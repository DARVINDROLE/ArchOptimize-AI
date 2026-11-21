"""Remember models that just failed, and skip them for a while."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class Cooldown:
    def __init__(self, seconds: float, clock: Callable[[], float] = time.monotonic):
        self._seconds = seconds
        self._clock = clock
        self._until: dict[str, float] = {}
        self._lock = threading.Lock()

    def mark(self, model_id: str) -> None:
        with self._lock:
            self._until[model_id] = self._clock() + self._seconds

    def is_cooling(self, model_id: str) -> bool:
        with self._lock:
            until = self._until.get(model_id)
            if until is None:
                return False
            if self._clock() >= until:
                del self._until[model_id]
                return False
            return True
