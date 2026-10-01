from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerboseInspectionFormatTestCase:
    """One recorded inspection read rendered as a verbose line."""

    description: str
    sql: str
    row_count: int | None
    error: str | None
    expected_fragments: tuple[str, ...]
    expected_maximum_length: int


@dataclass(frozen=True)
class VerboseInspectionOutputTestCase:
    """Inspection reads recorded inside and after a verbose output context."""

    description: str
    enabled: bool
    records: tuple[tuple[str, float, int], ...]
    expected_stderr_lines: tuple[str, ...]
