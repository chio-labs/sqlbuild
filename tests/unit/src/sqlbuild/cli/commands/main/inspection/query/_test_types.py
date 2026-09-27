from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryExecutionErrorTestCase:
    description: str
    sql: str
    expected_message_fragment: str
    expected_code: str = "C108"
    expected_exit_code: int = 2
