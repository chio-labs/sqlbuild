"""Test case types for model migration state entrypoints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NewestEventTestCase:
    description: str
    events: tuple[tuple[str, str], ...]
    relation: str
    expected: tuple[str, str] | None
