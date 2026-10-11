"""Test case types for SQL analysis integration tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SiteRecorderTestCase:
    """One process calling the wheel through a product site, with or without the record dir."""

    description: str
    record_dir: str
    expected_rows: tuple[tuple[str, str, int], ...]
    expected_entry_point: str


@dataclass(frozen=True)
class RelationNamesTestCase:
    """SQL texts whose hard-coded relation names Python's walk recorded in a golden."""

    description: str
    queries: tuple[tuple[str, str | None], ...]
    expected_differences: list[tuple[int, str, object, object]]
