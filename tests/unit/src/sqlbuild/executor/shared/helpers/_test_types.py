from dataclasses import dataclass

from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.executor.shared.types import LifecycleNodeStatus


@dataclass(frozen=True)
class StatementRecorderTestCase:
    description: str
    statements: tuple[str, ...]
    log_message: str
    expected_snapshot: tuple[LifeCycleEvent, ...]


@dataclass(frozen=True)
class LifecycleSchedulerTestCase:
    description: str
    expected_order: tuple[str, ...]
    expected_statuses: tuple[LifecycleNodeStatus, ...]
    expected_skip_reasons: tuple[str | None, ...]


@dataclass(frozen=True)
class LifecycleSchedulerErrorTestCase:
    description: str
    expected_error_fragment: str
