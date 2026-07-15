from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.executor.contracts.types import ExecutionStatus


@dataclass(frozen=True)
class SourceFreshnessAppendEligibilityTestCase:
    description: str
    model_statuses: dict[str, ExecutionStatus]
    expected_insert_count: int


@dataclass(frozen=True)
class DbtSqlbuildWorkOutputTestCase:
    description: str
    expected_fragments: tuple[str, ...]
    unexpected_fragments: tuple[str, ...]
