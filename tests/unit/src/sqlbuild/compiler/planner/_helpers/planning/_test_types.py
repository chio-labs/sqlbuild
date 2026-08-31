from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.contract.models import RelationInfo, RetentionState
from sqlbuild.compiler.planner.types import RetentionDirection, RetentionPlanPhase


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
class PermanentRetentionPlanningTestCase:
    description: str
    existing_relations: dict[str, RelationInfo]
    observed_state: RetentionState | None
    expected_direction: RetentionDirection
    expected_phase: RetentionPlanPhase
    expected_statements: tuple[str, ...]
