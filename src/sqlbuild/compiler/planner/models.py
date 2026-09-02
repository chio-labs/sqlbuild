"""Planner domain models."""

from __future__ import annotations

import calendar
import re
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, ClassVar

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo, RetentionRequest
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    FunctionReturnColumn,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction, SqlTestParameterDeclaration
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    ChangeKind,
    GraphResourceKind,
    LocalNodePlanAction,
    LocalNodePlanReason,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
    RetentionDirection,
    RetentionPlanPhase,
    RunDespiteUnchangedMode,
    ScenarioArtifactKind,
    SchemaActionKind,
    SchemaChangeKind,
    SchemaColumnSource,
    SelectorKind,
    WarningSeverity,
)
from sqlbuild.compiler.source_freshness.models import (
    DirectSourceFreshnessPlanningResult,
)
from sqlbuild.runtime.contracts.types import ExecutionResourceKind
from sqlbuild.spec.contracts.models import (
    FutureCursorsConfig,
    LocalConfig,
    ProjectConfig,
    SeedCsvSettings,
    SourceEntry,
    StartCursorsConfig,
)
from sqlbuild.spec.contracts.types import (
    FutureCursorAction,
    MicrobatchLimitAction,
    SourceWriteStrategy,
)
from sqlbuild.sql_values.models import SqlValue


@dataclass(frozen=True)
class GraphNodeKey:
    """Neutral graph key matching fingerprint identity fields."""

    node_type: str
    node_name: str


@dataclass(frozen=True)
class SelectorExpansion:
    """One selector split into graph expansion flags and core text."""

    core: str
    upstream: bool = False
    downstream: bool = False


@dataclass(frozen=True)
class LocalNodePlanInput:
    """Local state used to classify one planner graph node."""

    fingerprint_exists: bool
    relation_exists: bool
    full_refresh: bool = False
    local_hash: str | None = None
    previous_hash: str | None = None


@dataclass(frozen=True)
class LocalNodePlanOutcome:
    """Local planner action and reason for one graph node."""

    action: LocalNodePlanAction
    reason: LocalNodePlanReason


@dataclass(frozen=True)
class ParsedScenarioArtifactName:
    """Parsed physical name for one planner-owned scenario artifact."""

    hash_prefix: str
    kind: str
    logical_name: str


@dataclass(frozen=True)
class GraphIdentityNode:
    """Neutral node input for dependency-aware identity resolution."""

    key: GraphNodeKey
    resource_kind: GraphResourceKind
    upstream_keys: tuple[GraphNodeKey, ...]
    local_hash: str | None


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
                    raise PlannerInputError(
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
                        raise PlannerInputError(
                            f"{field_name} value '{value}' is not a whole number"
                        )
                except InvalidOperation:
                    raise PlannerInputError(
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
    physical_target_max: str | None = field(default=None, compare=False)
    target_eligible_max: str | None = None
    target_relation: str | None = field(default=None, compare=False)
    destination_cursor_column: str | None = field(default=None, compare=False)
    input_evidence: tuple[CursorInputEvidence, ...] = field(default=(), compare=False)
    expected_watermark_count: int = field(default=0, compare=False)
    unavailable_watermark_tags: tuple[str, ...] = ()

    @property
    def watermarks_available(self) -> bool:
        """Return whether every required physical watermark value was available."""

        return not self.unavailable_watermark_tags


@dataclass(frozen=True)
class CursorBounds:
    """Effective cursor start and end values for one incremental model."""

    start: str
    end: str
    future_safety: FutureCursorSafetyEvidence | None = None
    maximum_start_safety: MaximumStartSafetyEvidence | None = None


@dataclass(frozen=True)
class CursorInputEvidence:
    """Observed bounds for one physical cursor input."""

    relation: str
    cursor_column: str
    minimum: str | None
    maximum: str


@dataclass(frozen=True)
class FutureCursorSafetyEvidence:
    """Structured evidence for one applied future-cursor cap."""

    action: FutureCursorAction
    max_distance: str
    invocation_time: str
    discovered_start: str
    discovered_end: str
    applied_start: str
    applied_end: str
    maximum_allowed_start: str
    maximum_allowed_end: str
    future_start_detected: bool
    future_end_detected: bool
    determining_relation: str | None
    determining_cursor_column: str | None
    inputs: tuple[CursorInputEvidence, ...] = ()


@dataclass(frozen=True)
class MaximumStartSafetyEvidence:
    """Structured evidence for an automatic-start eligibility decision."""

    action: FutureCursorAction
    max_ahead: str
    invocation_time: str
    physical_target_max: str
    highest_eligible_target_max: str | None
    effective_start: str
    maximum_allowed_start: str
    target_relation: str
    cursor_column: str


@dataclass(frozen=True)
class Duration:
    """A calendar-aware cursor-window duration (years/months plus fixed time units)."""

    _PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?:(\d+)y)?(?:(\d+)mo)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"
    )
    _MONTHS_PER_YEAR: ClassVar[int] = 12
    _SECONDS_PER_DAY: ClassVar[int] = 86_400
    _SECONDS_PER_HOUR: ClassVar[int] = 3_600
    _SECONDS_PER_MINUTE: ClassVar[int] = 60

    years: int = 0
    months: int = 0
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0

    @classmethod
    def parse(cls, value: str) -> Duration | None:
        """Parse a string like '1mo', '2mo', '1y6mo', '30d', '6h' into a Duration."""

        match: re.Match[str] | None = cls._PATTERN.match(value)
        if match is None:
            return None
        duration: Duration = cls(
            years=int(match.group(1) or 0),
            months=int(match.group(2) or 0),
            days=int(match.group(3) or 0),
            hours=int(match.group(4) or 0),
            minutes=int(match.group(5) or 0),
            seconds=int(match.group(6) or 0),
        )
        if duration.is_zero:
            return None
        return duration

    @property
    def is_zero(self) -> bool:
        """Return whether the duration is empty."""

        return self.total_months == 0 and self.fixed_seconds == 0

    @property
    def has_calendar_component(self) -> bool:
        """Return whether the duration includes variable-length years or months."""

        return self.total_months != 0

    @property
    def fixed_seconds(self) -> int:
        """Return the fixed-length portion (days and below) as whole seconds."""

        return (
            self.days * self._SECONDS_PER_DAY
            + self.hours * self._SECONDS_PER_HOUR
            + self.minutes * self._SECONDS_PER_MINUTE
            + self.seconds
        )

    @property
    def total_months(self) -> int:
        """Return the whole-month portion (years folded into months)."""

        return self.years * self._MONTHS_PER_YEAR + self.months

    @property
    def _fixed_timedelta(self) -> timedelta:
        return timedelta(
            days=self.days, hours=self.hours, minutes=self.minutes, seconds=self.seconds
        )

    def add_to(self, moment: datetime) -> datetime:
        """Return the moment advanced by this duration."""

        return (
            self._shift_months(moment=moment, months_delta=self.total_months)
            + self._fixed_timedelta
        )

    def subtract_from(self, moment: datetime) -> datetime:
        """Return the moment moved back by this duration."""

        return (
            self._shift_months(moment=moment, months_delta=-self.total_months)
            - self._fixed_timedelta
        )

    def _shift_months(self, *, moment: datetime, months_delta: int) -> datetime:
        if months_delta == 0:
            return moment
        total: int = (moment.year * self._MONTHS_PER_YEAR + (moment.month - 1)) + months_delta
        year: int = total // self._MONTHS_PER_YEAR
        month: int = total % self._MONTHS_PER_YEAR + 1
        day: int = min(moment.day, calendar.monthrange(year, month)[1])
        return moment.replace(year=year, month=month, day=day)


@dataclass(frozen=True)
class CursorInputRelation:
    """One cursor-bearing input relation for runtime range discovery."""

    relation: str
    cursor_column: str
    cursor_grain: str | None = None
    is_model_backed: bool = False
    is_runtime_produced: bool = False

    @property
    def is_runtime_owned(self) -> bool:
        """Return whether bounds must be discovered after scheduled upstream execution."""

        return self.is_runtime_produced


@dataclass(frozen=True)
class WarehouseFingerprints:
    """Latest direct fingerprints grouped by node type."""

    models: dict[str, Fingerprint] = field(default_factory=dict)
    functions: dict[str, Fingerprint] = field(default_factory=dict)
    seeds: dict[str, Fingerprint] = field(default_factory=dict)
    python_nodes: dict[tuple[str, str], Fingerprint] = field(default_factory=dict)


@dataclass(frozen=True)
class CursorSnapshotScope:
    """Execution selection used for cursor validation and runtime producer resolution."""

    model_keys: frozenset[CompiledObjectKey]
    runtime_producer_keys: frozenset[CompiledObjectKey]
    invocation_time: datetime | None = None
    start_cursor_config: StartCursorsConfig | None = None
    cursor_overrides: CursorOverrides | None = None


@dataclass(frozen=True)
class MaximumStartPolicyInputs:
    """Effective policy and materialization safety inputs for automatic starts."""

    config: StartCursorsConfig | None = None
    invocation_time: datetime | None = None
    incremental_strategy: str | None = None
    incremental_mode: str | None = None


@dataclass(frozen=True)
class WarehouseSnapshot:
    """Frozen point-in-time picture of warehouse state for planning."""

    existing_relations: dict[str, RelationInfo] = field(default_factory=dict)
    existing_columns: dict[str, tuple[ColumnInfo, ...]] = field(default_factory=dict)
    fingerprints: WarehouseFingerprints = field(default_factory=WarehouseFingerprints)
    cursor_snapshots: dict[str, ModelCursorSnapshot] = field(default_factory=dict)
    source_freshness_state_schemas: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SelectionStalenessNodeKey:
    """Neutral node identity for shared selection-aware staleness classification."""

    resource_type: str
    name: str


@dataclass(frozen=True)
class SelectionStalenessGraph:
    """Neutral graph inputs for selected-model stale warning classification."""

    upstream_deps: dict[SelectionStalenessNodeKey, tuple[SelectionStalenessNodeKey, ...]]
    selected_model_names: frozenset[str]
    run_model_names: frozenset[str]
    run_seed_names: frozenset[str]
    run_source_names: frozenset[str]
    changed_model_names: frozenset[str]
    changed_seed_names: frozenset[str]
    changed_source_names: frozenset[str]


@dataclass(frozen=True)
class SelectionStalenessWarning:
    """Neutral stale warning classification for one selected model."""

    model_name: str
    trigger_names: tuple[str, ...]


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
class RunDespiteUnchangedDecision:
    """One model-level changes-only override decision."""

    model_name: str
    mode: RunDespiteUnchangedMode
    duration: str | None = None
    newest_source_name: str | None = None
    newest_source_data_age_seconds: int | None = None


@dataclass(frozen=True)
class RunDespiteUnchangedPlanningResult:
    """Planner-time changes-only override roots and propagated stale models."""

    root_model_names: frozenset[str] = frozenset()
    stale_model_names: frozenset[str] = frozenset()
    decisions: dict[str, RunDespiteUnchangedDecision] = field(default_factory=dict)
    downstream_root_causes: dict[str, str] = field(default_factory=dict)


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
    config_changed: bool = False
    fingerprint_metadata_json: str | None = None
    previous_metadata_json: str | None = None
    fingerprint_version_hash: str | None = None
    previous_version_hash: str | None = None
    schema_findings: tuple[SchemaFinding, ...] = field(default_factory=tuple)
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.FORWARD_ONLY)
    )


@dataclass(frozen=True)
class PlannerScope:
    """Resolved graph scope for one planner invocation."""

    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]
    all_keys: dict[str, CompiledObjectKey]
    models_by_name: dict[str, CompiledModel]
    selected_keys: frozenset[CompiledObjectKey]
    execution_order: tuple[CompiledObjectKey, ...]
    user_selected_keys: frozenset[CompiledObjectKey] = frozenset()


@dataclass(frozen=True)
class PlannerWarehouseSnapshotResult:
    """Warehouse discovery phase output with its resolved planning scope."""

    scope: PlannerScope
    snapshot: WarehouseSnapshot


@dataclass(frozen=True)
class PlannerRelationsContext:
    """Resolved relation and source inputs for plan entry construction."""

    model_locations: dict[str, CompiledRelationLocation]
    seed_locations: dict[str, CompiledRelationLocation]
    function_locations: dict[str, CompiledRelationLocation]
    source_map: dict[str, SourceEntry]
    source_read_map: dict[str, SourceEntry]
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]]
    star_exclude_keyword: str


@dataclass(frozen=True)
class ModelPlanContext:
    """Relation lookups and source columns for building one model plan entry."""

    model_locations: dict[str, CompiledRelationLocation]
    models_by_name: dict[str, CompiledModel]
    seed_locations: dict[str, CompiledRelationLocation]
    function_locations: dict[str, CompiledRelationLocation]
    source_map: dict[str, SourceEntry]
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]]
    star_exclude_keyword: str
    runtime_cursor_producer_names: frozenset[str] = frozenset()
    future_cursor_config: FutureCursorsConfig | None = None
    start_cursor_config: StartCursorsConfig | None = None
    invocation_time: datetime | None = None


@dataclass(frozen=True)
class CursorOverridePair:
    """Resolved per-model cursor start/end overrides for plan entry construction."""

    start_cursor_override: str | None = None
    end_cursor_override: str | None = None


@dataclass(frozen=True)
class ModelChangesPlanInputs:
    """Optional planning inputs for building a plan output from model changes."""

    cursor_overrides: CursorOverrides | None = None
    full_refresh: bool = False
    reload_sources: bool = False
    deferred_locations: dict[str, CompiledRelationLocation] | None = None
    project_config: ProjectConfig | None = None
    local_config: LocalConfig | None = None
    defer_sources_to: str | None = None
    source_deferral_enabled: bool = True
    seed_version_hashes: dict[str, str] | None = None
    seed_metadata_jsons: dict[str, str] | None = None
    seed_plan_reasons: dict[str, PlanReason] | None = None
    max_microbatches: int | None = None


@dataclass(frozen=True)
class PlanEntryBuildInputs:
    """Blocked models and cursor overrides for plan entry building."""

    run_despite_unchanged: RunDespiteUnchangedPlanningResult | None = None
    source_freshness_blocked_model_names: frozenset[str] = frozenset()
    external_blocked_model_names: frozenset[str] = frozenset()
    start_cursor_override: str | None = None
    end_cursor_override: str | None = None
    future_cursor_config: FutureCursorsConfig | None = None
    start_cursor_config: StartCursorsConfig | None = None
    invocation_time: datetime | None = None
    max_microbatches: int | None = None
    microbatch_limit_action: MicrobatchLimitAction = MicrobatchLimitAction.ERROR


@dataclass(frozen=True)
class FunctionChangeResult:
    """Per-function output from change detection."""

    fingerprint_sql: str
    reason: PlanReason = PlanReason.NO_CHANGE
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.FORWARD_ONLY)
    )


@dataclass(frozen=True)
class PlannerChangeResults:
    """Change detection output for selected planner resources."""

    models: dict[str, ChangeDetectionResult]
    functions: dict[str, FunctionChangeResult]


@dataclass(frozen=True)
class ResolvedModelAction:
    """Effective model change and backfill after cascade resolution."""

    change: ChangeDetectionResult
    backfill: BackfillResult
    cascade: CascadeResult | None = None


@dataclass(frozen=True)
class PlannerResolvedActions:
    """Cascade-resolved planning decisions keyed by model name."""

    models: dict[str, ResolvedModelAction]


@dataclass(frozen=True)
class DirectModelVersionIdentities:
    """Current direct model version identity values by model name."""

    function_local_hashes: dict[str, str]
    seed_version_hashes: dict[str, str]
    seed_metadata_jsons: dict[str, str]
    model_metadata_jsons: dict[str, str]
    model_local_hashes: dict[str, str]
    model_version_hashes: dict[str, str]


@dataclass(frozen=True)
class PlannerModelEntryResults:
    """Model plan-entry phase output."""

    entries: tuple[ModelPlanEntry, ...]
    warnings: tuple[PlanWarning, ...] = field(default_factory=tuple)


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
    code: str | None = None


@dataclass(frozen=True)
class RetentionPlanEntry:
    """Warehouse retention work independent of model identity actions."""

    request: RetentionRequest
    model_names: tuple[str, ...]
    actual_days: int | None
    effective_days: int | None
    source: str
    direction: RetentionDirection
    phase: RetentionPlanPhase
    statements: tuple[str, ...] = field(default_factory=tuple)
    irreversible_warning: str | None = None


@dataclass(frozen=True)
class TableTypePlanEntry:
    """Snowflake table-type work independent of model identity actions."""

    model_name: str
    destination: CompiledRelationLocation
    copy_name: str
    desired_type: str
    actual_type: str | None
    source: str
    downgrade: bool
    downgrade_policy: str
    irreversible_warning: str | None = None


@dataclass(frozen=True)
class PlanOutputExtras:
    """Optional supplemental seed fingerprints for plan output assembly."""

    seed_version_hashes: dict[str, str] | None = None
    seed_metadata_jsons: dict[str, str] | None = None
    seed_plan_reasons: dict[str, PlanReason] | None = None


@dataclass(frozen=True)
class ModelPlanEntry:
    """Per-model execution plan entry with action, reason, and resolved artifacts."""

    key: CompiledObjectKey
    name: str
    relative_path: Path
    materialization_type: MaterializationType
    action: PlanAction
    reason: PlanReason
    destination: CompiledRelationLocation
    fingerprint_query_sql: str
    resolved_sql: str
    logical_ddl: str
    incremental_strategy: str | None = None
    incremental_mode: str | None = None
    cursor_column: str | None = None
    cursor_type: str | None = None
    cursor_grain: str | None = None
    cursor_start: str | None = None
    lookback: str | None = None
    cursor_bounds: CursorBounds | None = None
    cursor_input_relations: tuple[CursorInputRelation, ...] = field(default_factory=tuple)
    batch_size: str | None = None
    batch_concurrency: int = 1
    unaccounted_partition_policy: str | None = None
    microbatch_range: CursorBounds | None = None
    microbatch_limit: int | None = None
    microbatch_limit_count: int | None = None
    microbatch_limit_action: MicrobatchLimitAction | None = None
    microbatch_limit_warning: str | None = None
    start_cursor_override: str | None = None
    end_cursor_override: str | None = None
    future_cursor_config: FutureCursorsConfig | None = None
    start_cursor_config: StartCursorsConfig | None = None
    invocation_time: datetime | None = None
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    merge_exclude_columns: tuple[str, ...] = field(default_factory=tuple)
    snapshot_strategy: str | None = None
    updated_at_column: str | None = None
    check_columns: tuple[str, ...] = field(default_factory=tuple)
    observed_at_column: str | None = None
    historical_input: str | None = None
    valid_from_column: str | None = None
    valid_to_column: str | None = None
    initial_valid_from: str | None = None
    invalidate_hard_deletes: bool = False
    snapshot_full_refresh: str | None = None
    snapshot_schema_change: str | None = None
    table_type: str = "transient"
    on_schema_change: OnSchemaChange | None = None
    type_enforcement: bool = False
    declared_columns: tuple[ColumnInfo, ...] = field(default_factory=tuple)
    contract_enforced: bool = False
    contract_columns: tuple[ColumnInfo, ...] = field(default_factory=tuple)
    pre_hooks: object = None
    post_hooks: object = None
    previous_query_sql: str | None = None
    fingerprint_metadata_json: str | None = None
    previous_metadata_json: str | None = None
    fingerprint_version_hash: str | None = None
    previous_version_hash: str | None = None
    query_changed: bool = False
    config_changed: bool = False
    schema_actions: tuple[SchemaAction, ...] = field(default_factory=tuple)
    schema_findings: tuple[SchemaFinding, ...] = field(default_factory=tuple)
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.FORWARD_ONLY)
    )
    cascade: CascadeResult | None = None
    custom_materialization_name: str | None = None
    custom_config: dict[str, object] = field(default_factory=dict)
    custom_placeholders: dict[str, str] = field(default_factory=dict)
    run_despite_unchanged: RunDespiteUnchangedDecision | None = None


@dataclass(frozen=True)
class CloneSourcePlanEntry:
    """One managed source relation selected for target cloning."""

    key: CompiledObjectKey
    name: str
    destination: CompiledRelationLocation


@dataclass(frozen=True)
class SeedPlanEntry:
    """Per-seed execution plan entry."""

    key: CompiledObjectKey
    name: str
    destination: CompiledRelationLocation
    file_path: Path
    columns: tuple[ColumnInfo, ...]
    csv_settings: SeedCsvSettings
    fingerprint_definition: str = ""
    fingerprint_version_hash: str = ""
    fingerprint_metadata_json: str = "{}"
    action: PlanAction = PlanAction.LOAD_SEED
    reason: PlanReason = PlanReason.FIRST_RUN


@dataclass(frozen=True)
class SourceLoadPlanEntry:
    """Per-managed-source loader execution plan entry."""

    key: CompiledObjectKey
    name: str
    loader: str
    destination: str
    resource_kind: ExecutionResourceKind = ExecutionResourceKind.SOURCE
    write_strategy: SourceWriteStrategy | None = None
    cursor_column: str | None = None
    unique_key: tuple[str, ...] = field(default_factory=tuple)
    is_reload: bool = False
    integration_kind: str | None = None


@dataclass(frozen=True)
class FunctionPlanEntry:
    """Per-SQL-function execution plan entry."""

    key: CompiledObjectKey
    name: str
    relative_path: Path
    destination: CompiledRelationLocation
    arguments: tuple[object, ...]
    returns: str
    body_sql: str
    fingerprint_query_sql: str
    fingerprint_destination: CompiledRelationLocation
    return_columns: tuple[FunctionReturnColumn, ...] = field(default_factory=tuple)
    language: FunctionLanguage = FunctionLanguage.SQL
    source_file_path: Path | None = None
    runtime_version: str | None = None
    entry_point: str | None = None
    packages: tuple[str, ...] = field(default_factory=tuple)
    previous_query_sql: str | None = None
    reason: PlanReason = PlanReason.NO_CHANGE
    backfill: BackfillResult = field(
        default_factory=lambda: BackfillResult(action=BackfillAction.FORWARD_ONLY)
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
    always_run: bool = False


@dataclass(frozen=True)
class ChainStep:
    """One step in a chained test execution sequence."""

    model_name: str
    resolved_sql: str
    expected_cte_sql: str | None = None


@dataclass(frozen=True)
class SqlTestAssertionStep:
    """One zero-row assertion step in a SQL-native unit test."""

    name: str
    resolved_sql: str


@dataclass(frozen=True)
class SqlAnalysisResolvedTestSql:
    """SQL analysis-resolved test SQL plus reusable CTE state for downstream refs."""

    resolved_sql: str
    cte_body_sql: str
    generated_ctes: OrderedDict[str, str]
    reachable_mock_names: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SqlTestPlanEntry:
    """Per-test execution plan entry with chained resolution."""

    key: CompiledObjectKey
    name: str
    source_path: Path | None = None
    block_index: int | None = None
    parent_name: str | None = None
    case_name: str | None = None
    case_index: int | None = None
    case_fingerprint: str | None = None
    parameter_schema: tuple[SqlTestParameterDeclaration, ...] = field(default_factory=tuple)
    parameter_values: tuple[tuple[str, SqlValue], ...] = field(default_factory=tuple)
    chain: tuple[ChainStep, ...] = field(default_factory=tuple)
    assertions: tuple[SqlTestAssertionStep, ...] = field(default_factory=tuple)
    scope_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    function_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    sql_analysis_enabled: bool = True


@dataclass(frozen=True)
class ScenarioGraphPlan:
    """Inferred graph slice and fixture boundaries for one SQL scenario."""

    key: CompiledObjectKey
    name: str
    target_model_names: tuple[str, ...] = field(default_factory=tuple)
    assertion_target_model_names: tuple[str, ...] = field(default_factory=tuple)
    model_names: tuple[str, ...] = field(default_factory=tuple)
    source_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    seed_names: tuple[str, ...] = field(default_factory=tuple)
    seed_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    dbt_ref_fixture_names: tuple[str, ...] = field(default_factory=tuple)
    function_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScenarioArtifactIdentity:
    """Logical identity for one scenario-owned physical artifact."""

    kind: ScenarioArtifactKind | str
    logical_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ScenarioArtifactKind(self.kind))


@dataclass(frozen=True)
class ScenarioArtifactName:
    """Resolved physical relation name for one scenario artifact."""

    identity: ScenarioArtifactIdentity
    physical_name: str


@dataclass(frozen=True)
class ScenarioRelationMap:
    """Resolved scenario hash prefix and scenario-owned relation names."""

    scenario_name: str
    hash_prefix: str
    artifacts: tuple[ScenarioArtifactName, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScenarioRelationPlan:
    """Resolved scenario relation locations for model/source/seed ref resolution."""

    scenario_name: str
    relation_map: ScenarioRelationMap
    model_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    seed_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    project_source_map: dict[str, SourceEntry] = field(default_factory=dict)
    source_map: dict[str, SourceEntry] = field(default_factory=dict)
    source_fixture_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    ref_fixture_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    seed_fixture_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    dbt_ref_fixture_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)


@dataclass(frozen=True)
class ScenarioFixturePlan:
    """Self-contained fixture SQL planned for scenario materialization."""

    kind: ScenarioArtifactKind
    logical_name: str
    destination: CompiledRelationLocation
    sql: str


@dataclass(frozen=True)
class ScenarioExpectedExpectationPlan:
    """Expected-output comparison inputs for one scenario target model."""

    model_name: str
    actual_destination: CompiledRelationLocation
    expected_sql: str


@dataclass(frozen=True)
class ScenarioAssertionExpectationPlan:
    """Zero-row assertion SQL for one scenario assertion CTE."""

    name: str
    sql: str


@dataclass(frozen=True)
class ScenarioExecutionPlan:
    """Dry-run execution plan for a SQL scenario graph slice."""

    key: CompiledObjectKey
    name: str
    graph_plan: ScenarioGraphPlan
    relation_plan: ScenarioRelationPlan
    fixture_plans: tuple[ScenarioFixturePlan, ...] = field(default_factory=tuple)
    seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    function_entries: tuple[FunctionPlanEntry, ...] = field(default_factory=tuple)
    model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    hook_functions: tuple[DiscoveredHookFunction, ...] = field(default_factory=tuple)
    expected_expectations: tuple[ScenarioExpectedExpectationPlan, ...] = field(
        default_factory=tuple
    )
    assertion_expectations: tuple[ScenarioAssertionExpectationPlan, ...] = field(
        default_factory=tuple
    )


@dataclass(frozen=True)
class PlanProviderUsage:
    """Provider usage metadata scoped to planned work."""

    provider_name: str
    consumer_kind: str
    consumer_name: str
    parameter_name: str
    annotation_class_name: str | None = None
    annotation_module: str | None = None


@dataclass(frozen=True)
class PlanOutput:
    """Complete execution plan produced by the planner."""

    execution_order: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    source_load_entries: tuple[SourceLoadPlanEntry, ...] = field(default_factory=tuple)
    function_entries: tuple[FunctionPlanEntry, ...] = field(default_factory=tuple)
    audit_entries: tuple[AuditPlanEntry, ...] = field(default_factory=tuple)
    test_entries: tuple[SqlTestPlanEntry, ...] = field(default_factory=tuple)
    selected_keys: frozenset[CompiledObjectKey] = field(default_factory=frozenset)
    warnings: tuple[PlanWarning, ...] = field(default_factory=tuple)
    retention_entries: tuple[RetentionPlanEntry, ...] = field(default_factory=tuple)
    table_type_entries: tuple[TableTypePlanEntry, ...] = field(default_factory=tuple)
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = field(
        default_factory=dict
    )
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = field(
        default_factory=dict
    )
    model_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    seed_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    function_locations: dict[str, CompiledRelationLocation] = field(default_factory=dict)
    source_map: dict[str, SourceEntry] = field(default_factory=dict)
    source_read_map: dict[str, SourceEntry] = field(default_factory=dict)
    hook_functions: tuple[DiscoveredHookFunction, ...] = field(default_factory=tuple)
    provider_usages: tuple[PlanProviderUsage, ...] = field(default_factory=tuple)
    source_freshness: DirectSourceFreshnessPlanningResult | None = None
    python_identity_fingerprints: dict[tuple[str, str], Fingerprint] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class PlannerSelection:
    """User-facing selection inputs for one planner invocation."""

    select: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    selected_keys: frozenset[CompiledObjectKey] | None = None


@dataclass(frozen=True)
class PlannerOverrides:
    """Explicit user overrides that force or bound planner decisions."""

    cursor_overrides: CursorOverrides | None = None
    full_refresh: bool = False
    reload_sources: bool = False
    forced_stale_model_names: tuple[str, ...] = ()
    external_blocked_model_names: tuple[str, ...] = ()
    max_microbatches: int | None = None


@dataclass(frozen=True)
class DeferralInputs:
    """Deferred relation and source-deferral inputs for planning."""

    deferred_locations: dict[str, CompiledRelationLocation] | None = None
    deferred_relations: dict[str, RelationInfo] | None = None
    defer_sources_to: str | None = None
    source_deferral_enabled: bool = True


@dataclass(frozen=True)
class PlannerPolicies:
    """Behavior policies selected by the caller for one planner invocation."""

    auto_load_sources: bool = False
    selection_diagnostics: bool = False


@dataclass(frozen=True)
class PlannerRuntime:
    """Resolved execution environment shared by planner phases."""

    project: CompiledProject
    adapter: BaseAdapter
    connection: Any
    project_config: ProjectConfig | None = None
    local_config: LocalConfig | None = None
    on_progress: Callable[[str], None] | None = None
    invocation_time: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class PlannerScopeResolution:
    """Resolved planner scopes for one plan build."""

    selected_scope: PlannerScope
    stale_warning_scope: PlannerScope
    inspection_scope: PlannerScope


@dataclass(frozen=True)
class PlannerWarehouseState:
    """Warehouse snapshot and inspection relations gathered once per plan."""

    snapshot: WarehouseSnapshot
    inspection_relations: PlannerRelationsContext


@dataclass(frozen=True)
class PlannerIdentityContext:
    """Expected version identities for inspection and stale-warning scopes."""

    version_identities: DirectModelVersionIdentities
    stale_warning_identities: DirectModelVersionIdentities


@dataclass(frozen=True)
class PlannerScopePruningResult:
    """Scope pruning outcome with pruned scopes, actions, and staleness state."""

    inspection_scope: PlannerScope
    execution_scope: PlannerScope
    resolved_actions: PlannerResolvedActions
    pruned_direct_model_names: tuple[str, ...]
    direct_identity_stale_model_names: frozenset[str]
    run_despite_unchanged: RunDespiteUnchangedPlanningResult


@dataclass(frozen=True)
class PlannerChangeReconciliation:
    """Write-hash-honest changes merged back into resolved actions."""

    changes: PlannerChangeResults
    resolved_actions: PlannerResolvedActions


@dataclass(frozen=True)
class PlannerEntryResults:
    """Model plan entries for one plan build."""

    model_entry_results: PlannerModelEntryResults
