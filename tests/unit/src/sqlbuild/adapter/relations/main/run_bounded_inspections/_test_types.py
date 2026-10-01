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
