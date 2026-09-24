from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JanitorEventWriteTestCase:
    description: str
    write_attempts: int
    expected_row_count: int
    expected_write_results: tuple[bool, ...]
