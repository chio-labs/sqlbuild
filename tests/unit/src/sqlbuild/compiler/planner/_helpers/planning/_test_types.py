from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.adapter.contract.models import RetentionState
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
