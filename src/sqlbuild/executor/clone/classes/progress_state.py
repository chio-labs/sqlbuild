"""Thread-safe clone progress state."""

from __future__ import annotations

import threading


class CloneProgressState:
    """Hold identity-stable clone progress shared with the spinner thread."""

    def __init__(self) -> None:
        self._completed: int = 0
        self._total: int | None = None
        self._lock: threading.Lock = threading.Lock()

    def update(self, *, completed: int, total: int) -> CloneProgressState:
        with self._lock:
            self._completed = completed
            self._total = total
        return self

    def snapshot(self) -> tuple[int, int | None]:
        with self._lock:
            return self._completed, self._total
