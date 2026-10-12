"""Test case types for SQL analysis integration tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RelationNamesTestCase:
    """SQL texts whose hard-coded relation names Python's walk recorded in a golden."""

    description: str
    queries: tuple[tuple[str, str | None], ...]
    expected_differences: list[tuple[int, str, object, object]]
