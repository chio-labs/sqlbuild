from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.models import QueryResult


@dataclass(frozen=True)
class MotherDuckQueryTestCase:
    description: str
    sql: str
    expected_result: QueryResult


@dataclass(frozen=True)
class MotherDuckBuildFlowTestCase:
    description: str
    table_name: str
    source_sql: str
    expected_row_count: int
