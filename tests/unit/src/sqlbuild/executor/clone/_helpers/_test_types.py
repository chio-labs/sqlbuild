from dataclasses import dataclass

from sqlbuild.compiler.planner.types import RetentionPlanPhase
from sqlbuild.executor.clone.types import CloneAction, CloneStatus


@dataclass(frozen=True)
class CloneRelationExecutionTestCase:
    description: str
    hard_copy: bool
    supports_zero_copy_clone: bool
    expected_action: CloneAction
    expected_status: CloneStatus
    expected_statements: tuple[str, ...]
    origin_is_transient: bool = False


@dataclass(frozen=True)
class CloneRetentionTestCase:
    description: str
    desired_days: int
    effective_days: int
    is_transient: bool
    expected_statements: tuple[str, ...] = ()
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class CloneNamespaceRetentionPhaseTestCase:
    description: str
    desired_days: int
    effective_days: int
    phase: RetentionPlanPhase
    expected_statements: tuple[str, ...]
