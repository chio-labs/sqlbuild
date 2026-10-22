from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JanitorEventWriterTestCase:
    description: str
    record_count: int
    written_before: int
    write_now_first: bool
    expected_row_count: int
    expected_insert_count: int
    expected_existence_query_count: int
