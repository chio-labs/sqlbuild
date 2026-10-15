"""Test case types for the planner differential baseline comparison."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompareDocumentsTestCase:
    """A baseline and an actual run, and the artifacts reported as different."""

    description: str
    expected: dict[str, object]
    actual: dict[str, object]
    expected_artifacts: tuple[str, ...]
