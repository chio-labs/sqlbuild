from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NativeSqlTestErrorTestCase:
    """One failing SQL test, scenario or relationship project compiled by every engine."""

    description: str
    case_name: str
    expected_distinct_macro_call_counts: int
