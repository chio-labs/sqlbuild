from dataclasses import dataclass

from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.scheduling.types import LifecycleNodeStatus


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


@dataclass(frozen=True)
class LifecycleSchedulerFanInTestCase:
    description: str
    expected_calls: list[str]
    expected_statuses: tuple[LifecycleNodeStatus, ...]
    expected_downstream_skip_reason: str | None
    expected_downstream_skip_mode: SkipMode | None
