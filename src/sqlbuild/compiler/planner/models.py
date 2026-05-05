"""Planner domain models."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledRelationTarget,
    FunctionReturnColumn,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
    SchemaActionKind,
    SchemaChangeKind,
    SchemaColumnSource,
    SelectorKind,
    WarningSeverity,
)
from sqlbuild.spec.models.schema import SeedCsvSettings
from sqlbuild.spec.models.source import SourceEntry


@dataclass(frozen=True)
class CursorOverrides:
    """Typed cursor override values from CLI flags."""

    start_ts: str | None = None
    end_ts: str | None = None
    start_int: str | None = None
    end_int: str | None = None

    def __post_init__(self) -> None:
        field_name: str
        value: str | None
        for field_name, value in (
            ("--start-cursor-ts", self.start_ts),
            ("--end-cursor-ts", self.end_ts),
        ):
            if value is not None:
                try:
                    datetime.fromisoformat(value)
                except (ValueError, TypeError) as error:
                    raise ValueError(
                        f"{field_name} value '{value}' is not a valid ISO timestamp: {error}"
                    ) from None
        for field_name, value in (
            ("--start-cursor-int", self.start_int),
            ("--end-cursor-int", self.end_int),
        ):
            if value is not None:
                try:
                    decimal_value: Decimal = Decimal(value)
                    if decimal_value != int(decimal_value):
                        raise ValueError(f"{field_name} value '{value}' is not a whole number")
                except InvalidOperation:
                    raise ValueError(
                        f"{field_name} value '{value}' is not a valid integer"
                    ) from None


@dataclass(frozen=True)
class MissingUpstream:
    """One upstream dependency missing from both scope and warehouse."""

    key: CompiledObjectKey
    required_by: tuple[CompiledObjectKey, ...]


@dataclass(frozen=True)
class ParsedSelector:
    """One parsed selector token before graph resolution."""

    kind: SelectorKind
    value: str
    upstream: bool = False
    downstream: bool = False


@dataclass(frozen=True)
class PathSelector:
    """A directed path selector between two model names with optional endpoint expansion."""

    start_name: str
    end_name: str
    upstream: bool = False
    downstream: bool = False


@dataclass(frozen=True)
class ModelCursorSnapshot:
    """Cursor MIN/MAX values gathered from warehouse for one incremental model."""

    target_max: str | None
    upstream_mins: tuple[str, ...]
    upstream_maxes: tuple[str, ...]


@dataclass(frozen=True)
class CursorBounds:
    """Effective cursor start and end values for one incremental model."""

    start: str
    end: str


@dataclass(frozen=True)
class CursorInputRelation:
    """One cursor-bearing input relation for runtime range discovery."""

    relation: str
    cursor_column: str
    cursor_grain: str | None = None
    is_model_backed: bool = False


@dataclass(frozen=True)
class WarehouseSnapshot:
    """Frozen point-in-time picture of warehouse state for planning."""

    existing_relations: dict[str, RelationInfo] = field(default_factory=dict)
    existing_columns: dict[str, tuple[ColumnInfo, ...]] = field(default_factory=dict)
    fingerprints: dict[str, Fingerprint] = field(default_factory=dict)
    cursor_snapshots: dict[str, ModelCursorSnapshot] = field(default_factory=dict)


@dataclass(frozen=True)
class SchemaFinding:
    """One detected schema difference between expected and warehouse columns."""

    kind: SchemaChangeKind
    column_name: str
    source: SchemaColumnSource
    expected_type: str | None = None
    actual_type: str | None = None


@dataclass(frozen=True)
class BackfillResult:
    """Resolved backfill action from a change detection policy."""

    action: BackfillAction
    duration: str | None = None


@dataclass(frozen=True)
class CascadeCause:
    """One upstream model that contributed to a backfill cascade."""

    model_name: str
    effective_action: BackfillAction
    effective_duration: str | None
    root_cause: str | None = None
    root_reason: PlanReason | None = None


@dataclass(frozen=True)
class CascadeResult:
    """Effective backfill after upstream cascade propagation."""

    effective_action: BackfillAction
    effective_duration: str | None
    root_cause: str | None
    root_reason: PlanReason | None = None
    causes: tuple[CascadeCause, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ChangeDetectionResult:
    """Per-model output from change detection and policy resolution."""

    model_name: str
    change_kind: ChangeKind
    query_changed: bool = False
    schema_findings: tuple[SchemaFinding, ...] = field(default_factory=tuple)
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.WARN_ONLY)
    )


@dataclass(frozen=True)
class SchemaAction:
    """One concrete schema change action to apply to a target table."""

    kind: SchemaActionKind
    column_name: str
    column_type: str | None = None


@dataclass(frozen=True)
class PlanWarning:
    """One warning or error produced during plan resolution."""

    model_name: str | None
    severity: WarningSeverity
    message: str


@dataclass(frozen=True)
class ModelPlanEntry:
    """Per-model execution plan entry with action, reason, and resolved artifacts."""

    key: CompiledObjectKey
    name: str
    relative_path: Path
    materialization_type: MaterializationType
    action: PlanAction
    reason: PlanReason
    target: CompiledRelationTarget
    fingerprint_query_sql: str
    resolved_sql: str
    logical_ddl: str
    incremental_strategy: str | None = None
    incremental_mode: str | None = None
    cursor_column: str | None = None
    cursor_type: str | None = None
    cursor_grain: str | None = None
    cursor_start: str | None = None
    cursor_bounds: CursorBounds | None = None
    cursor_input_relations: tuple[CursorInputRelation, ...] = field(default_factory=tuple)
    batch_size: str | None = None
    microbatch_range: CursorBounds | None = None
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    on_schema_change: OnSchemaChange | None = None
    type_enforcement: bool = False
    declared_columns: tuple[ColumnInfo, ...] = field(default_factory=tuple)
    pre_hook: object = None
    post_hook: object = None
    previous_query_sql: str | None = None
    schema_actions: tuple[SchemaAction, ...] = field(default_factory=tuple)
    schema_findings: tuple[SchemaFinding, ...] = field(default_factory=tuple)
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.WARN_ONLY)
    )
    cascade: CascadeResult | None = None
    custom_materialization_name: str | None = None
    custom_config: dict[str, object] = field(default_factory=dict)
    custom_placeholders: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SeedPlanEntry:
    """Per-seed execution plan entry."""

    key: CompiledObjectKey
    name: str
    target: CompiledRelationTarget
    file_path: Path
    columns: tuple[ColumnInfo, ...]
    csv_settings: SeedCsvSettings
    action: PlanAction = PlanAction.LOAD_SEED


@dataclass(frozen=True)
class FunctionPlanEntry:
    """Per-SQL-function execution plan entry."""

    key: CompiledObjectKey
    name: str
    relative_path: Path
    target: CompiledRelationTarget
    arguments: tuple[object, ...]
    returns: str
    body_sql: str
    fingerprint_query_sql: str
    fingerprint_target: CompiledRelationTarget
    return_columns: tuple[FunctionReturnColumn, ...] = field(default_factory=tuple)
    language: FunctionLanguage = FunctionLanguage.SQL
    source_file_path: Path | None = None
    runtime_version: str | None = None
    entry_point: str | None = None
    packages: tuple[str, ...] = field(default_factory=tuple)
    previous_query_sql: str | None = None
    reason: PlanReason = PlanReason.NO_CHANGE
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.WARN_ONLY)
    )


@dataclass(frozen=True)
class AuditPlanEntry:
    """Per-audit execution plan entry with resolved SQL and scheduling metadata."""

    key: CompiledObjectKey
    name: str
    resolved_sql: str
    unresolved_sql: str
    attachment_kind: AuditAttachmentKind
    severity: AuditSeverity
    requested_run_scope: AuditRunScope
    effective_run_scope: AuditRunScope
    scope_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    attached_target_name: str | None = None
    attached_column_name: str | None = None


@dataclass(frozen=True)
class ChainStep:
    """One step in a chained test execution sequence."""

    model_name: str
    resolved_sql: str
    expected_cte_sql: str


@dataclass(frozen=True)
class SqlglotResolvedTestSql:
    """SQLGlot-resolved test SQL plus reusable CTE state for downstream refs."""

    resolved_sql: str
    cte_body_sql: str
    generated_ctes: OrderedDict[str, str]


@dataclass(frozen=True)
class SqlTestPlanEntry:
    """Per-test execution plan entry with chained resolution."""

    key: CompiledObjectKey
    name: str
    chain: tuple[ChainStep, ...] = field(default_factory=tuple)
    scope_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    function_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PlanOutput:
    """Complete execution plan produced by the planner."""

    execution_order: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    function_entries: tuple[FunctionPlanEntry, ...] = field(default_factory=tuple)
    audit_entries: tuple[AuditPlanEntry, ...] = field(default_factory=tuple)
    test_entries: tuple[SqlTestPlanEntry, ...] = field(default_factory=tuple)
    selected_keys: frozenset[CompiledObjectKey] = field(default_factory=frozenset)
    warnings: tuple[PlanWarning, ...] = field(default_factory=tuple)
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = field(
        default_factory=dict
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = field(
        default_factory=dict
    )
    model_targets: dict[str, CompiledRelationTarget] = field(default_factory=dict)
    seed_targets: dict[str, CompiledRelationTarget] = field(default_factory=dict)
    function_targets: dict[str, CompiledRelationTarget] = field(default_factory=dict)
    source_map: dict[str, SourceEntry] = field(default_factory=dict)
