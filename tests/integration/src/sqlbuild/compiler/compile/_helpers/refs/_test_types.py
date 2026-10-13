from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CraftedReferenceTestCase:
    """One SQL text and how many calls the native scan rejects or fails on."""

    description: str
    sql: str
    expected_rejected: int = 0
    expected_failed: int = 0


@dataclass(frozen=True)
class ReferenceExtractionTestCase:
    """Reference extraction through the compiler entry point."""

    description: str
    sql: str
    expected_references: tuple[tuple[str, str, str | None, int | None], ...] = ()
    expected_error: str = ""


@dataclass(frozen=True)
class ReferenceScanBoundTestCase:
    """A worst-case SQL shape the native scan must finish within a strict time limit."""

    description: str
    sql: str
    expected_outcome: int | str
    expected_maximum_seconds: float
