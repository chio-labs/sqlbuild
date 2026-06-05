from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.executor.shared.types import ExecutionStatus


@dataclass(frozen=True)
class SourceFreshnessAppendEligibilityTestCase:
    description: str
    model_statuses: dict[str, ExecutionStatus]
    expected_insert_count: int
