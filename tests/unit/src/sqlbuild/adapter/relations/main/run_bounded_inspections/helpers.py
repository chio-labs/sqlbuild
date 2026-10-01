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


def _return_index(index: int) -> int:
    return index


def _interrupt(index: int) -> int:
    raise KeyboardInterrupt(f"interrupted at read {index}")


class StartRecordingTasks:
    """Tasks with per-index latency that record which indexes started."""

    def __init__(
        self,
        *,
        latencies: tuple[float, ...],
        outcomes: dict[int, Callable[[int], int]],
    ) -> None:
        self._latencies: tuple[float, ...] = latencies
        self._outcomes: dict[int, Callable[[int], int]] = outcomes
        self._lock: threading.Lock = threading.Lock()
        self.started: list[int] = []

    def tasks(self) -> tuple[Callable[[], int], ...]:
        """Return one task per configured latency."""

        return tuple(self._task(index=index) for index in range(len(self._latencies)))

    def _task(self, *, index: int) -> Callable[[], int]:
        def run() -> int:
            with self._lock:
                self.started.append(index)
            time.sleep(self._latencies[index])
            return self._outcomes.get(index, _return_index)(index)

        return run


def interrupting_outcomes(*, interrupt_in_task: bool) -> dict[int, Callable[[int], int]]:
    """Interrupt read 0 inside the task, or nowhere when the callback interrupts instead."""

    outcomes: tuple[dict[int, Callable[[int], int]], ...] = ({}, {0: _interrupt})
    return outcomes[interrupt_in_task]


def failing_outcomes(indexes: frozenset[int]) -> dict[int, Callable[[int], int]]:
    """Fail the given reads with their index in the message."""

    return dict.fromkeys(indexes, _fail)


def interrupt_on_first_completion(*, interrupt: bool) -> Callable[..., None]:
    """Return a completion callback that interrupts the coordinating thread when asked."""

    def complete(*, index: int, result: int) -> None:
        del result
        (_ignore_completion, _interrupt)[interrupt](index)

    return complete


def _ignore_completion(index: int) -> int:
    return index
