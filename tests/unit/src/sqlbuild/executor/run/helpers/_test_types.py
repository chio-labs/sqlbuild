from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import ColumnInfo, LifeCycleEvent
from sqlbuild.executor.shared.types import ExecutionPhase


@dataclass(frozen=True)
class BuildQualifiedNameTestCase:
    description: str
    adapter_name: str
    database: str | None
    schema: str | None
    name: str
    expected_qualified: str


@dataclass(frozen=True)
class BuildFailedResultTestCase:
    description: str
    error: str | BaseException
    recorded_statements: tuple[str, ...]
    warning_messages: tuple[str, ...]
    expected_model_name: str
    expected_error_message: str
    expected_error_code: str
    expected_lifecycle_events: tuple[LifeCycleEvent, ...]


@dataclass(frozen=True)
class RuntimeCursorStartTestCase:
    description: str
    target_max: object | None
    upstream_min: object
    upstream_max: object
    cursor_type: str
    cursor_start: str | None
    expected_start: str
    expected_end: str


@dataclass(frozen=True)
class RuntimeTargetMaxTestCase:
    description: str
    target_rows: tuple[object, ...]
    upstream_min: object
    upstream_max: object
    cursor_type: str
    expected_start: str
    expected_end: str


@dataclass(frozen=True)
class RuntimeTargetProbeFailureTestCase:
    description: str
    expected_error_type: type[BaseException]


@dataclass(frozen=True)
class SnapshotAdapterRenderingTestCase:
    description: str
    expected_rendered_marker: str


@dataclass(frozen=True)
class SnapshotLifecycleTestCase:
    description: str
    run_id: str
    pre_hook: tuple[object, ...]
    post_hook: tuple[object, ...]
    expected_hook_events: tuple[str, ...]
    expected_model_name: str
    expected_target_name: str
    hook_functions: tuple[object, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SnapshotHookFailureTestCase:
    description: str
    pre_hooks: object
    post_hooks: object
    expected_phase: ExecutionPhase
    expected_error_fragment: str


@dataclass(frozen=True)
class RenderHooksTestCase:
    description: str
    hooks: object
    expected_statements: tuple[str, ...]


@dataclass(frozen=True)
class PublicHookContextExportTestCase:
    description: str
    expected_export_name: str


@dataclass(frozen=True)
class ExecuteHooksTestCase:
    description: str
    hooks: object
    expected_rows: tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class PythonHookExecutionTestCase:
    description: str
    hooks: object
    expected_error_fragment: str


@dataclass(frozen=True)
class PythonHookInvocationTestCase:
    description: str
    expected_message: str
    expected_rows: list[tuple[object, ...]]
    expected_model_name: str
    expected_phase: str
    expected_hook_name: str
    expected_hook_index: int
    expected_run_id: str
    expected_environment: str
    expected_vars: dict[str, object]
    expected_destination_name: str
    expected_destination_schema: str
    expected_adapter_name: str
    expected_recorded_events: tuple[str, ...]


@dataclass(frozen=True)
class PythonHookContextParameterTestCase:
    description: str
    hook_name: str
    expected_context_count: int
    expected_return_ignored: object


@dataclass(frozen=True)
class PythonHookRuntimeErrorTestCase:
    description: str
    expected_error_fragment: str


@dataclass(frozen=True)
class SnapshotRuntimeContractErrorTestCase:
    description: str
    contract_columns: tuple[ColumnInfo, ...]
    run_id: str
    expected_error_fragment: str


@dataclass(frozen=True)
class SnapshotSchemaChangeTestCase:
    description: str
    target_columns: tuple[ColumnInfo, ...]
    delta_columns: tuple[ColumnInfo, ...]
    expected_valid: bool
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class RuntimeContractValidationTestCase:
    description: str
    contract_enforced: bool
    contract_columns: tuple[ColumnInfo, ...]
    actual_columns: tuple[ColumnInfo, ...]
    expected_valid: bool
    expected_error_fragment: str | None = None
    expected_error_code: str | None = None
