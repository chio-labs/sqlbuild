"""One shared daemon that runs deferred thread starts once their deadline passes."""

from __future__ import annotations

import heapq
import itertools
import threading
import time
from collections.abc import Callable

type _DeferredStart = tuple[float, int, Callable[[], None]]


class DeferredThreadStarts:
    """Run each scheduled start callback at its monotonic deadline on one shared thread."""

    def __init__(self, *, name: str) -> None:
        self._name: str = name
        self._condition: threading.Condition = threading.Condition()
        self._pending: list[_DeferredStart] = []
        self._order: itertools.count[int] = itertools.count()
        self._thread: threading.Thread | None = None

    def schedule(self, *, delay_seconds: float, start: Callable[[], None]) -> None:
        """Call ``start`` after ``delay_seconds``; the callback must tolerate a stopped owner."""

        entry: _DeferredStart = (time.monotonic() + delay_seconds, next(self._order), start)
        with self._condition:
            heapq.heappush(self._pending, entry)
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
                self._thread.start()
            elif self._pending[0] is entry:
                self._condition.notify()

    def _run(self) -> None:
        while True:
            start: Callable[[], None] = self._next_due()
            try:
                start()
            except BaseException:
                pass

    def _next_due(self) -> Callable[[], None]:
        with self._condition:
            while True:
                if not self._pending:
                    _ = self._condition.wait()
                    continue
                remaining: float = self._pending[0][0] - time.monotonic()
                if remaining <= 0:
                    return heapq.heappop(self._pending)[2]
                _ = self._condition.wait(remaining)
