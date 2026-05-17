from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MotherDuckBuildE2ETestCase:
    description: str
    command: tuple[str, ...]
    expected_table_name: str
    expected_row_count: int
    expected_stdout_fragments: tuple[str, ...]
    expected_return_code: int = 0
