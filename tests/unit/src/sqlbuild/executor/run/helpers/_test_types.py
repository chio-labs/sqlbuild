from dataclasses import dataclass

from sqlbuild.adapter.shared.models import ColumnInfo, LifeCycleEvent


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


@dataclass(frozen=True)
class RenderHooksTestCase:
    description: str
    hooks: object
    expected_statements: tuple[str, ...]


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
