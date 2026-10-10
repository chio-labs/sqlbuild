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
    expected_input_relations: tuple[str, ...] = ()
    aggregate: str = "MAX"


@dataclass(frozen=True)
class SetOperationSearchTestCase:
    description: str
    seed: int
    count: int
    expected_minimum_matches: int
