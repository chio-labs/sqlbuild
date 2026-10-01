from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundedInspectionTestCase:
    """Independent reads run with a concurrency bound."""

    description: str
    task_count: int
    concurrency: int
    expected_results: tuple[int, ...]
    expected_parallel: bool


@dataclass(frozen=True)
class BoundedInspectionFailureTestCase:
    """Independent reads where some fail."""

    description: str
    task_count: int
    concurrency: int
    failing_indexes: frozenset[int]
    expected_error: str


@dataclass(frozen=True)
class InterruptedInspectionTestCase:
    """A KeyboardInterrupt while bounded reads are queued."""

    description: str
    task_count: int
    concurrency: int
    task_seconds: float
    interrupt_in_task: bool
    expected_max_seconds: float
    expected_max_started: int


@dataclass(frozen=True)
class InFlightFailureTestCase:
    """Failures from tasks that were already running when the first failure arrived."""

    description: str
    task_seconds: tuple[float, ...]
    failing_indexes: frozenset[int]
    concurrency: int
    expected_error: str
