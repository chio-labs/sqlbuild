from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompileSqlReference
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind
from sqlbuild.compiler.planner.models import (
    MissingUpstream,
    ParsedSelector,
    PathSelector,
    SchemaAction,
    SchemaFinding,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
    WarningSeverity,
)


@dataclass(frozen=True)
class BuildUpstreamDepsTestCase:
    description: str
    model_deps: dict[str, tuple[str, ...]]
    source_names: tuple[str, ...]
    seed_names: tuple[str, ...]
    expected_upstream_keys: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class BuildDownstreamDepsTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_downstream_keys: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]


@dataclass(frozen=True)
class TopologicalOrderTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_order: tuple[CompiledObjectKey, ...]


@dataclass(frozen=True)
class CycleDetectionTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class ExpandUpstreamTestCase:
    description: str
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    key: CompiledObjectKey
    expected_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class ExpandDownstreamTestCase:
    description: str
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    key: CompiledObjectKey
    expected_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class FindPathKeysTestCase:
    description: str
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    start: CompiledObjectKey
    end: CompiledObjectKey
    expected_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class FindPathKeysErrorTestCase:
    description: str
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    start: CompiledObjectKey
    end: CompiledObjectKey
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class ParseSelectorTestCase:
    description: str
    raw: str
    expected_result: ParsedSelector | PathSelector


@dataclass(frozen=True)
class ParseSelectorErrorTestCase:
    description: str
    raw: str
    expected_error_type: type[Exception]


@dataclass(frozen=True)
class ResolveSelectorTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_names: frozenset[str]


@dataclass(frozen=True)
class ResolveSelectorErrorTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_error_type: type[Exception]
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class CheckBuildabilityTestCase:
    description: str
    selected_keys: frozenset[CompiledObjectKey]
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    existing_relation_names: tuple[str, ...]
    expected_missing: tuple[MissingUpstream, ...]
    deferred_relation_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResolveModelPlanActionTestCase:
    description: str
    materialized: str
    incremental_strategy: str | None
    change_kind: ChangeKind
    query_changed: bool
    backfill_action: BackfillAction
    full_refresh: bool
    expected_action: PlanAction
    expected_reason: PlanReason
    schema_findings: tuple[SchemaFinding, ...] = field(default_factory=tuple)
    backfill_duration: str | None = None
    enabled: bool | None = None


@dataclass(frozen=True)
class IncrementalStrategyErrorTestCase:
    description: str
    materialized: str
    incremental_strategy: str | None
    change_kind: ChangeKind
    expected_error_type: type[Exception]
    expected_error_fragment: str


@dataclass(frozen=True)
class ResolveSchemaActionsTestCase:
    description: str
    schema_findings: tuple[SchemaFinding, ...]
    on_schema_change: OnSchemaChange | None
    expected_actions: tuple[SchemaAction, ...]


@dataclass(frozen=True)
class BuildLogicalDdlTestCase:
    description: str
    action: PlanAction
    resolved_sql: str
    qualified_name: str | None
    unique_key: tuple[str, ...]
    warehouse_columns: tuple[ColumnInfo, ...]
    expected_ddl_fragment: str


@dataclass(frozen=True)
class BuildModelWarningsTestCase:
    description: str
    model_name: str
    materialization_type: MaterializationType
    change_kind: ChangeKind
    query_changed: bool
    backfill_action: BackfillAction
    schema_findings: tuple[SchemaFinding, ...]
    schema_actions: tuple[SchemaAction, ...]
    on_schema_change: OnSchemaChange | None
    type_enforcement: bool
    expected_severity: WarningSeverity | None
    expected_warning_count: int
    expected_severities: tuple[WarningSeverity, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BuildPathIndexTestCase:
    description: str
    model_paths: dict[str, str]
    expected_folders: dict[str, str]


@dataclass(frozen=True)
class PlanAuditTestCase:
    description: str
    sql_body: str
    model_targets: dict[str, str]
    source_map_entries: dict[str, tuple[str | None, str, str | None]]
    expected_sql_fragment: str


@dataclass(frozen=True)
class ApplyDeferredTargetsTestCase:
    description: str
    model_target_names: tuple[str, ...]
    seed_target_names: tuple[str, ...]
    deferred_target_names: tuple[str, ...]
    selected_key_names: tuple[str, ...]
    expected_model_qualified_names: dict[str, str | None]
    expected_seed_qualified_names: dict[str, str | None]


@dataclass(frozen=True)
class CursorUpstreamResolutionTestCase:
    description: str
    ref_name: str
    model_qualified_name: str | None
    deferred_qualified_name: str | None
    selected_names: frozenset[str] | None
    expected_qualified_name: str | None


@dataclass(frozen=True)
class CursorOverrideResolutionTestCase:
    description: str
    cursor_type: str | None
    start_ts: str | None
    end_ts: str | None
    start_int: str | None
    end_int: str | None
    generic_start: str | None
    generic_end: str | None
    expected_start: str | None
    expected_end: str | None


@dataclass(frozen=True)
class MicrobatchLookbackTestCase:
    description: str
    incremental_strategy: str
    batch_size: str
    lookback: str | None
    expected_lookback: str | None


@dataclass(frozen=True)
class CursorOverridesValidationTestCase:
    description: str
    start_ts: str | None = None
    end_ts: str | None = None
    start_int: str | None = None
    end_int: str | None = None
    expected_valid: bool = True
    expected_error_fragment: str | None = None


@dataclass(frozen=True)
class CursorStartBoundsTestCase:
    description: str
    target_max: str | None
    upstream_mins: tuple[str, ...]
    upstream_maxes: tuple[str, ...]
    cursor_type: str
    cursor_start: str | None
    lookback: str | None
    backfill_duration: str | None
    start_cursor_override: str | None
    end_cursor_override: str | None
    expected_start: str | None
    expected_end: str | None


@dataclass(frozen=True)
class CursorTypeCheckTestCase:
    description: str
    cursor_column: str | None
    cursor_type: str | None
    warehouse_columns: tuple[tuple[str, str], ...]
    sqlglot_enabled: bool
    expected_warning: bool
    expected_severity: WarningSeverity | None = None
    expected_message_fragment: str | None = None


@dataclass(frozen=True)
class ResolveCascadeTestCase:
    description: str
    own_action: BackfillAction
    own_duration: str | None
    own_cursor_type: str | None
    upstream_entries: tuple[tuple[str, BackfillAction, str | None, str | None], ...]
    expected_cascade: bool
    expected_action: BackfillAction | None = None
    expected_duration: str | None = None
    expected_root_cause: str | None = None
    expected_cause_count: int = 0


@dataclass(frozen=True)
class ResolveAttachmentTestCase:
    description: str
    references: tuple[CompileSqlReference, ...]
    attached_target_kind: AttachedAuditTargetKind | None
    attached_target_name: str | None
    upstream_edges: dict[str, tuple[str, ...]]
    expected_attachment_kind: AuditAttachmentKind
    expected_attached_name: str | None


@dataclass(frozen=True)
class ResolveAttachmentErrorTestCase:
    description: str
    references: tuple[CompileSqlReference, ...]
    attached_target_kind: AttachedAuditTargetKind | None
    attached_target_name: str | None
    upstream_edges: dict[str, tuple[str, ...]]
    expected_error_fragment: str


@dataclass(frozen=True)
class ResolveEffectiveRunScopeTestCase:
    description: str
    requested_run_scope: AuditRunScope
    attached_model_materialization: str | None
    expected_effective_run_scope: AuditRunScope
