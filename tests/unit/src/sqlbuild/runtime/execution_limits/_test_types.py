from dataclasses import dataclass

from sqlbuild.runtime.execution_limits.models import ItemTimeoutPolicy
from sqlbuild.runtime.execution_limits.types import CancellationOutcome, ItemKind
from tests.unit.src.sqlbuild.runtime.execution_limits.helpers import FakeCancellingAdapter


@dataclass(frozen=True)
class RunItemTimeoutsTestCase:
    description: str
    run_limit: str | None
    run_seconds: int | None
    overrides_items: bool
    declared: str | None
    declared_seconds: int | None
    expected_policy: ItemTimeoutPolicy | None


@dataclass(frozen=True)
class DeadlineCancellationTestCase:
    description: str
    interrupt_result: bool
    adapter_type: type[FakeCancellingAdapter]
    asynchronous: bool
    statement_query_id: str | None
    expected_outcome: CancellationOutcome


@dataclass(frozen=True)
class IdleExpiryTestCase:
    description: str
    kind: ItemKind
    expected_outcome: CancellationOutcome
    expected_interrupted: bool


@dataclass(frozen=True)
class SuspendedCleanupTestCase:
    description: str
    expected_enforced: bool


@dataclass(frozen=True)
class EarliestDeadlineTestCase:
    description: str
    build_seconds: int
    item_seconds: int
    expected_item_is_current: bool


@dataclass(frozen=True)
class NoPolicyTestCase:
    description: str
    expected_deadline: None
