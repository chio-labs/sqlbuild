"""Helpers for bounded inspection read tests."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


def _succeed(index: int) -> int:
    return index * 10


def _fail(index: int) -> int:
    raise RuntimeError(f"read {index} failed")


_OUTCOMES: dict[bool, Callable[[int], int]] = {False: _succeed, True: _fail}
_LATENCIES: tuple[float, float] = (0.02, 0.005)


class ConcurrencyTracker:
    """Build read tasks that record how many run at once."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._active: int = 0
        self.max_active: int = 0

    def tasks(self, *, count: int, failing: frozenset[int]) -> tuple[Callable[[], int], ...]:
        """Return ``count`` tasks; even tasks are slower so finish order differs from input."""

        return tuple(self._task(index=index, failing=failing) for index in range(count))

    def _task(self, *, index: int, failing: frozenset[int]) -> Callable[[], int]:
        def run() -> int:
            with self._lock:
                self._active += 1
                self.max_active = max(self.max_active, self._active)
            try:
                time.sleep(_LATENCIES[index % 2])
                return _OUTCOMES[index in failing](index)
            finally:
                with self._lock:
                    self._active -= 1

        return run
