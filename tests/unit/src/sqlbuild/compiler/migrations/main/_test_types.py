"""Test case types for model migration state entrypoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewestEventTestCase:
    description: str
    events: tuple[tuple[str, str], ...]
    relation: str
    expected_newest_index: int | None


@dataclass(frozen=True)
class RepeatedEventWriteTestCase:
    description: str
    write_count: int
    expected_stored_count: int


@dataclass(frozen=True)
class ColumnEventStorageTestCase:
    description: str
    write_count: int
    foreign_decisions: tuple[str, ...]
    expected_stored_count: int


@dataclass(frozen=True)
class NewestColumnEventTestCase:
    description: str
    renames: tuple[tuple[str, str], ...]
    origin_column: str
    destination_column: str
    expected_newest_index: int | None
