from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DynamicPivotAnalysisTestCase:
    description: str
    dialect: str
    query_sql: str
    expected_proven: bool
    expected_fixed_columns: tuple[str, ...] = ()
    expected_failure_fragment: str = ""
    expected_family_types: tuple[str | None, ...] = ("DECIMAL(12,2)",)
    aggregate: str = "MAX"
