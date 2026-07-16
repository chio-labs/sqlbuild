from dataclasses import dataclass

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
