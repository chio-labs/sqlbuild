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
