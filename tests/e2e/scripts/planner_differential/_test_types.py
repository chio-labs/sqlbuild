"""Test case types for the planner differential end-to-end tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecordCheckTestCase:
    """A record run, a check of the same tree, and a check against a tampered baseline."""

    description: str
    project: str
    steps: tuple[str, ...]
    tampered_step_index: int
    expected_artifacts: tuple[str, ...]
    expected_clean_line: str
    expected_difference_line: str
    expected_diff_line: str
    expected_note: str
