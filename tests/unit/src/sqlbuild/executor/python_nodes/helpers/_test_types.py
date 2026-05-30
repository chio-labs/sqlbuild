from dataclasses import dataclass

from sqlbuild.compiler.python_nodes.types import (
    PythonNodeFanInAction,
    PythonNodeKind,
    PythonNodeStatus,
    SkipMode,
)


@dataclass(frozen=True)
class PythonNodeSchedulerTestCase:
    description: str
    node_names: tuple[str, ...]
    upstream_names: dict[str, tuple[str, ...]]
    downstream_names: dict[str, tuple[str, ...]]
    completion_order: tuple[str, ...]
    expected_initial_ready: tuple[str, ...]
    expected_final_ready: tuple[str, ...]
    expected_final_in_degree: dict[str, int]


@dataclass(frozen=True)
class PythonNodeReturnNormalizationTestCase:
    description: str
    kind: PythonNodeKind
    returned: object
    expected_status: PythonNodeStatus
    expected_payload: object | None
    expected_metadata: dict[str, object]
    expected_materialized: bool | None
    expected_skip_mode: SkipMode | None
    expected_skip_reason: str | None


@dataclass(frozen=True)
class PythonNodeFanInPolicyTestCase:
    description: str
    upstream_statuses: tuple[PythonNodeStatus, ...]
    upstream_skip_modes: tuple[SkipMode | None, ...]
    expected_action: PythonNodeFanInAction
    expected_reason: str | None


@dataclass(frozen=True)
class PythonNodeFailureResultTestCase:
    description: str
    error: BaseException
    expected_status: PythonNodeStatus
    expected_error_message: str


@dataclass(frozen=True)
class PythonNodeReturnNormalizationErrorTestCase:
    description: str
    kind: PythonNodeKind
    returned: object
    expected_error_fragment: str
