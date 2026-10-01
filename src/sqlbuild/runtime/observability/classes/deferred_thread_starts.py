"""One shared daemon that runs deferred thread starts once their deadline passes."""

from __future__ import annotations

import heapq
import itertools
import threading
import time
from collections.abc import Callable

type _DeferredDeadline = tuple[float, int]

_COMPACTION_SLACK: int = 64


class DeferredThreadStarts:
    """Run each scheduled start callback at its monotonic deadline on one shared thread."""

    def __init__(self, *, name: str) -> None:
        self._name: str = name
        self._condition: threading.Condition = threading.Condition()
        self._deadlines: list[_DeferredDeadline] = []
        self._starts: dict[int, Callable[[], None]] = {}
        self._order: itertools.count[int] = itertools.count()
        self._thread: threading.Thread | None = None

    @property
    def pending_count(self) -> int:
        """Return how many scheduled starts have neither run nor been cancelled."""

        with self._condition:
            return len(self._starts)

    def schedule(self, *, delay_seconds: float, start: Callable[[], None]) -> int:
        """Call ``start`` after ``delay_seconds`` unless cancelled; return its cancel token."""

        token: int = next(self._order)
        deadline: _DeferredDeadline = (time.monotonic() + delay_seconds, token)
        with self._condition:
            self._starts[token] = start
            heapq.heappush(self._deadlines, deadline)
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
                self._thread.start()
            elif self._deadlines[0] is deadline:
                self._condition.notify()
        return token

    def cancel(self, token: int) -> None:
        """Drop a scheduled start so nothing it references outlives its owner."""

        with self._condition:
            if self._starts.pop(token, None) is None:
                return
            if len(self._deadlines) > 2 * len(self._starts) + _COMPACTION_SLACK:
                self._deadlines = [
                    deadline for deadline in self._deadlines if deadline[1] in self._starts
                ]
                heapq.heapify(self._deadlines)

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
                if not self._deadlines:
                    _ = self._condition.wait()
                    continue
                due_at, token = self._deadlines[0]
                remaining: float = due_at - time.monotonic()
                if remaining > 0:
                    _ = self._condition.wait(remaining)
                    continue
                heapq.heappop(self._deadlines)
                start: Callable[[], None] | None = self._starts.pop(token, None)
                if start is not None:
                    return start
