from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner.models import (
    MissingUpstream,
    ParsedSelector,
    SchemaAction,
    SchemaFinding,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
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
    expected_result: ParsedSelector | tuple[str, str]


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


@dataclass(frozen=True)
class CheckBuildabilityTestCase:
    description: str
    selected_keys: frozenset[CompiledObjectKey]
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    existing_relation_names: tuple[str, ...]
    expected_missing: tuple[MissingUpstream, ...]


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
class PlanAuditTestCase:
    description: str
    sql_body: str
    model_targets: dict[str, str]
    source_map_entries: dict[str, tuple[str | None, str, str | None]]
    expected_sql_fragment: str
