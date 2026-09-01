from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.contract.models import RetentionState
from sqlbuild.compiler.planner.types import RetentionDirection, RetentionPlanPhase
from sqlbuild.spec.contracts.types import TableType, TableTypeDowngradePolicy


@dataclass(frozen=True)
class RetentionPlanningTestCase:
    description: str
    desired_days: int
    observed_state: RetentionState
    expected_direction: RetentionDirection
    expected_phase: RetentionPlanPhase


@dataclass(frozen=True)
class RetentionPlanningErrorTestCase:
    description: str
    desired_days: int
    expected_error_fragment: str


@dataclass(frozen=True)
class TableTypePlanningTestCase:
    description: str
    desired_type: TableType
    live_is_transient: bool | None
    relation_exists: bool
    downgrade_policy: TableTypeDowngradePolicy
    expected_entry_count: int
    expected_actual_type: str | None
    expected_downgrade: bool
    materialized: str = "table"
    additional_config: tuple[tuple[str, object], ...] = ()
    relation_type: str = "BASE TABLE"
