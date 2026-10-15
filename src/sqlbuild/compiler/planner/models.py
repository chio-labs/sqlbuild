"""Planner domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlbuild._native import (
    BackfillResult,
    ColumnRenameHint,
    CursorWatermarkMode,
    DateValue,
    DirectSourceFreshnessPlanningResult,
    Fingerprint,
    FunctionReturnColumn,
    FutureCursorAction,
    FutureCursorsConfig,
    GraphResourceKind,
    IntegerValue,
    MeasurementThresholds,
    MicrobatchLimitAction,
    MigrationCompatibility,
    MigrationDiscovery,
    MissingMigrationOriginPolicy,
    OldNameViewAction,
    PlanProviderUsage,
    PlanWarning,
    ScenarioArtifactName,
    ScenarioGraphPlan,
    SchemaAction,
    SchemaChangeKind,
    SchemaColumnSource,
    SchemaDynamicColumnFamily,
    SeedCsvSettings,
    SourceEntry,
    SourceWriteStrategy,
    SqlTestAssertionStep,
    SqlValue,
    StartCursorsConfig,
    TimestampValue,
)
from sqlbuild._native import Duration as Duration
from sqlbuild._native import cursor_parse as parse
from sqlbuild.adapter.contract.models import ColumnInfo, RetentionRequest
from sqlbuild.adapter.contract.types import MigrationTransfer
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditEvaluationMode,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    FunctionLanguage,
)
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction, SqlTestParameterDeclaration
from sqlbuild.compiler.migrations.types import (
    ColumnMigrationDecision,
    MigrationDecision,
    MigrationPromotion,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    CursorGrain,
    CursorType,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
    RetentionDirection,
    RetentionPlanPhase,
    ScenarioArtifactKind,
)
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.types import Bound, BoundSentinel, CursorScalar
from sqlbuild.runtime.contracts.types import ExecutionResourceKind


@dataclass(frozen=True, kw_only=True, init=False)
class CursorOverrides:
    """Cursor override values from CLI flags; untyped `start`/`end` await planner typing."""

    start_ts: CursorScalar | None = None
    end_ts: CursorScalar | None = None
    start_int: CursorScalar | None = None
    end_int: CursorScalar | None = None
    start: str | None = None
    end: str | None = None

    def __init__(
        self,
        *,
        start_ts: str | CursorScalar | None = None,
        end_ts: str | CursorScalar | None = None,
        start_int: str | CursorScalar | None = None,
        end_int: str | CursorScalar | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> None:
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(
            self,
            "start_ts",
            self._parse_timestamp(field_name="--start-cursor-ts", value=start_ts),
        )
        object.__setattr__(
            self, "end_ts", self._parse_timestamp(field_name="--end-cursor-ts", value=end_ts)
        )
        object.__setattr__(
            self,
            "start_int",
            self._parse_integer(field_name="--start-cursor-int", value=start_int),
        )
        object.__setattr__(
            self, "end_int", self._parse_integer(field_name="--end-cursor-int", value=end_int)
        )

    @property
    def has_untyped(self) -> bool:
        """Return whether `--start-cursor` or `--end-cursor` still needs a cursor type."""

        return self.start is not None or self.end is not None

    def typed_as(self, *, cursor_type: CursorType) -> CursorOverrides:
        """Return these overrides with `--start-cursor`/`--end-cursor` read as `cursor_type`."""

        if not self.has_untyped:
            return self
        if cursor_type == CursorType.INTEGER:
            return CursorOverrides(
                start_ts=self.start_ts,
                end_ts=self.end_ts,
                start_int=self._parse_integer(field_name="--start-cursor", value=self.start)
                or self.start_int,
                end_int=self._parse_integer(field_name="--end-cursor", value=self.end)
                or self.end_int,
            )
        return CursorOverrides(
            start_ts=self._parse_timestamp(field_name="--start-cursor", value=self.start)
            or self.start_ts,
            end_ts=self._parse_timestamp(field_name="--end-cursor", value=self.end) or self.end_ts,
            start_int=self.start_int,
            end_int=self.end_int,
        )

    @staticmethod
    def _parse_timestamp(
        *, field_name: str, value: str | CursorScalar | None
    ) -> CursorScalar | None:
        if value is None or not isinstance(value, str):
            return value
        try:
            datetime.fromisoformat(value)
        except (ValueError, TypeError) as error:
            raise PlannerInputError(
                f"{field_name} value '{value}' is not a valid ISO timestamp: {error}"
            ) from None
        return parse(raw=value, cursor_type="timestamp")

    @staticmethod
    def _parse_integer(*, field_name: str, value: str | CursorScalar | None) -> CursorScalar | None:
        if value is None or not isinstance(value, str):
            return value
        try:
            decimal_value: Decimal = Decimal(value)
            if decimal_value != int(decimal_value):
                raise PlannerInputError(f"{field_name} value '{value}' is not a whole number")
            parsed: CursorScalar = parse(raw=value, cursor_type="integer")
            if isinstance(parsed, IntegerValue):
                return parsed
        except InvalidOperation:
            raise PlannerInputError(
                f"{field_name} value '{value}' is not a valid integer"
            ) from None
        raise PlannerInputError(f"{field_name} value '{value}' is not a valid integer")


@dataclass(frozen=True)
class EmptyCursorInputDecision:
    """Cursor inputs whose lack of rows leaves no window, and whether other inputs have rows."""

    input_names: tuple[str, ...] = ()
    waiting_on_empty_inputs: bool = False


@dataclass(frozen=True, kw_only=True, init=False)
class ModelCursorSnapshot:
    """Cursor MIN/MAX values gathered from warehouse for one incremental model."""

    target_max: CursorScalar | None
    upstream_mins: tuple[CursorScalar, ...]
    upstream_maxes: tuple[CursorScalar, ...]
    physical_target_max: CursorScalar | None = field(default=None, compare=False)
    target_eligible_max: CursorScalar | None = None
    target_relation: str | None = field(default=None, compare=False)
    destination_cursor_column: str | None = field(default=None, compare=False)
    input_evidence: tuple[CursorInputEvidence, ...] = field(default=(), compare=False)
    expected_watermark_count: int = field(default=0, compare=False)
    unavailable_watermark_tags: tuple[str, ...] = ()
    cursor_watermark_mode: CursorWatermarkMode = CursorWatermarkMode.ALL
    upstream_terminal_starts: tuple[CursorScalar, ...] = ()
    upstream_terminal_ends: tuple[CursorScalar, ...] = ()
    upstream_end_inputs: tuple[tuple[CursorScalar | None, CursorScalar | None], ...] = ()
    upstream_availability_ends: tuple[CursorScalar, ...] = ()
    empty_input_names: tuple[str, ...] = field(default=(), compare=False)
    unreadable_input_names: tuple[str, ...] = field(default=(), compare=False)

    def __init__(self, **values: Any) -> None:
        defaults: dict[str, object] = {
            "physical_target_max": None,
            "target_eligible_max": None,
            "target_relation": None,
            "destination_cursor_column": None,
            "input_evidence": (),
            "expected_watermark_count": 0,
            "unavailable_watermark_tags": (),
            "cursor_watermark_mode": CursorWatermarkMode.ALL,
            "upstream_terminal_starts": (),
            "upstream_terminal_ends": (),
            "upstream_end_inputs": (),
            "upstream_availability_ends": (),
            "empty_input_names": (),
            "unreadable_input_names": (),
        }
        defaults.update(values)
        field_name: str
        for field_name in self.__dataclass_fields__:
            object.__setattr__(self, field_name, defaults[field_name])
        self.__post_init__()

    def __post_init__(self) -> None:
        for field_name in ("target_max", "physical_target_max", "target_eligible_max"):
            object.__setattr__(
                self, field_name, CursorBounds._parse_optional(raw=getattr(self, field_name))
            )
        for field_name in (
            "upstream_mins",
            "upstream_maxes",
            "upstream_terminal_starts",
            "upstream_terminal_ends",
            "upstream_availability_ends",
        ):
            object.__setattr__(
                self,
                field_name,
                tuple(
                    CursorBounds._parse_inferred(raw=value) for value in getattr(self, field_name)
                ),
            )
        object.__setattr__(
            self,
            "upstream_end_inputs",
            tuple(
                (
                    CursorBounds._parse_optional(raw=physical),
                    CursorBounds._parse_optional(raw=terminal),
                )
                for physical, terminal in self.upstream_end_inputs
            ),
        )
        object.__setattr__(
            self, "cursor_watermark_mode", CursorWatermarkMode(self.cursor_watermark_mode)
        )

    @property
    def watermarks_available(self) -> bool:
        """Return whether every required physical watermark value was available."""

        return not self.unavailable_watermark_tags


@dataclass(frozen=True, kw_only=True, init=False)
class CursorBounds:
    """Effective cursor start and end values for one incremental model."""

    start: Bound
    end: Bound
    future_safety: FutureCursorSafetyEvidence | None = None
    maximum_start_safety: MaximumStartSafetyEvidence | None = None

    def __init__(
        self,
        *,
        start: Bound | str,
        end: Bound | str,
        future_safety: FutureCursorSafetyEvidence | None = None,
        maximum_start_safety: MaximumStartSafetyEvidence | None = None,
    ) -> None:
        object.__setattr__(self, "start", CursorBounds._parse_bound(raw=start))
        object.__setattr__(self, "end", CursorBounds._parse_bound(raw=end))
        object.__setattr__(self, "future_safety", future_safety)
        object.__setattr__(self, "maximum_start_safety", maximum_start_safety)

    @staticmethod
    def _parse_inferred(*, raw: object) -> CursorScalar:
        if isinstance(raw, TimestampValue | DateValue | IntegerValue):
            return raw
        try:
            return parse(raw=str(raw), cursor_type="integer")
        except CursorAlgebraError:
            return parse(raw=str(raw), cursor_type="timestamp")

    @staticmethod
    def _parse_optional(*, raw: object | None) -> CursorScalar | None:
        return None if raw is None else CursorBounds._parse_inferred(raw=raw)

    @staticmethod
    def _parse_bound(*, raw: object) -> Bound:
        if isinstance(raw, BoundSentinel):
            return raw
        if raw == BoundSentinel.START.value:
            return BoundSentinel.START
        if raw == BoundSentinel.END.value:
            return BoundSentinel.END
        return CursorBounds._parse_inferred(raw=raw)


@dataclass(frozen=True, kw_only=True, init=False)
class CursorInputEvidence:
    """Observed bounds for one physical cursor input."""

    relation: str
    cursor_column: str
    minimum: CursorScalar | None
    maximum: CursorScalar

    def __init__(
        self,
        *,
        relation: str,
        cursor_column: str,
        minimum: CursorScalar | str | None,
        maximum: CursorScalar | str,
    ) -> None:
        object.__setattr__(self, "relation", relation)
        object.__setattr__(self, "cursor_column", cursor_column)
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        self.__post_init__()

    def __post_init__(self) -> None:
        object.__setattr__(self, "minimum", CursorBounds._parse_optional(raw=self.minimum))
        object.__setattr__(self, "maximum", CursorBounds._parse_inferred(raw=self.maximum))


@dataclass(frozen=True, kw_only=True, init=False)
class FutureCursorSafetyEvidence:
    """Structured evidence for one applied future-cursor cap."""

    action: FutureCursorAction
    max_distance: str
    invocation_time: CursorScalar
    discovered_start: CursorScalar
    discovered_end: CursorScalar
    applied_start: CursorScalar
    applied_end: CursorScalar
    maximum_allowed_start: CursorScalar
    maximum_allowed_end: CursorScalar
    future_start_detected: bool
    future_end_detected: bool
    determining_relation: str | None
    determining_cursor_column: str | None
    inputs: tuple[CursorInputEvidence, ...] = ()

    def __init__(self, **values: Any) -> None:
        values.setdefault("inputs", ())
        field_name: str
        for field_name in self.__dataclass_fields__:
            object.__setattr__(self, field_name, values[field_name])
        self.__post_init__()

    def __post_init__(self) -> None:
        for field_name in (
            "invocation_time",
            "discovered_start",
            "discovered_end",
            "applied_start",
            "applied_end",
            "maximum_allowed_start",
            "maximum_allowed_end",
        ):
            object.__setattr__(
                self, field_name, CursorBounds._parse_inferred(raw=getattr(self, field_name))
            )


@dataclass(frozen=True, kw_only=True, init=False)
class MaximumStartSafetyEvidence:
    """Structured evidence for an automatic-start eligibility decision."""

    action: FutureCursorAction
    max_ahead: str
    invocation_time: CursorScalar
    physical_target_max: CursorScalar
    highest_eligible_target_max: CursorScalar | None
    effective_start: CursorScalar
    maximum_allowed_start: CursorScalar
    target_relation: str
    cursor_column: str

    def __init__(
        self,
        *,
        action: FutureCursorAction,
        max_ahead: str,
        invocation_time: CursorScalar | str,
        physical_target_max: CursorScalar | str,
        highest_eligible_target_max: CursorScalar | str | None,
        effective_start: CursorScalar | str,
        maximum_allowed_start: CursorScalar | str,
        target_relation: str,
        cursor_column: str,
    ) -> None:
        for field_name, value in (
            ("action", action),
            ("max_ahead", max_ahead),
            ("invocation_time", invocation_time),
            ("physical_target_max", physical_target_max),
            ("highest_eligible_target_max", highest_eligible_target_max),
            ("effective_start", effective_start),
            ("maximum_allowed_start", maximum_allowed_start),
            ("target_relation", target_relation),
            ("cursor_column", cursor_column),
        ):
            object.__setattr__(self, field_name, value)
        self.__post_init__()

    def __post_init__(self) -> None:
        for field_name in (
            "invocation_time",
            "physical_target_max",
            "effective_start",
            "maximum_allowed_start",
        ):
            object.__setattr__(
                self, field_name, CursorBounds._parse_inferred(raw=getattr(self, field_name))
            )
        object.__setattr__(
            self,
            "highest_eligible_target_max",
            CursorBounds._parse_optional(raw=self.highest_eligible_target_max),
        )


@dataclass(frozen=True, kw_only=True, init=False)
class CursorInputRelation:
    """One cursor-bearing input relation for runtime range discovery."""

    relation: str
    cursor_column: str
    cursor_grain: CursorGrain | None = None
    is_model_backed: bool = False
    is_runtime_produced: bool = False
    terminal_cursor_start: CursorScalar | None = None
    terminal_cursor_end: CursorScalar | None = None
    input_name: str | None = None
    input_kind: GraphResourceKind | None = None

    def __init__(
        self,
        *,
        relation: str,
        cursor_column: str,
        cursor_grain: CursorGrain | str | None = None,
        is_model_backed: bool = False,
        is_runtime_produced: bool = False,
        terminal_cursor_start: CursorScalar | str | None = None,
        terminal_cursor_end: CursorScalar | str | None = None,
        input_name: str | None = None,
        input_kind: GraphResourceKind | None = None,
    ) -> None:
        object.__setattr__(self, "relation", relation)
        object.__setattr__(self, "cursor_column", cursor_column)
        object.__setattr__(self, "cursor_grain", cursor_grain)
        object.__setattr__(self, "is_model_backed", is_model_backed)
        object.__setattr__(self, "is_runtime_produced", is_runtime_produced)
        object.__setattr__(self, "terminal_cursor_start", terminal_cursor_start)
        object.__setattr__(self, "terminal_cursor_end", terminal_cursor_end)
        object.__setattr__(self, "input_name", input_name)
        object.__setattr__(self, "input_kind", input_kind)
        self.__post_init__()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "cursor_grain",
            CursorGrain(self.cursor_grain) if self.cursor_grain is not None else None,
        )
        object.__setattr__(
            self,
            "terminal_cursor_start",
            CursorBounds._parse_optional(raw=self.terminal_cursor_start),
        )
        object.__setattr__(
            self, "terminal_cursor_end", CursorBounds._parse_optional(raw=self.terminal_cursor_end)
        )

    @property
    def is_runtime_owned(self) -> bool:
        """Return whether bounds must be discovered after scheduled upstream execution."""

        return self.is_runtime_produced


@dataclass(frozen=True)
class MaximumStartPolicyInputs:
    """Effective policy and materialization safety inputs for automatic starts."""

    config: StartCursorsConfig | None = None
    invocation_time: datetime | None = None
    incremental_strategy: str | None = None
    incremental_mode: str | None = None


@dataclass(frozen=True)
class SchemaFinding:
    """One detected schema difference between expected and warehouse columns."""

    kind: SchemaChangeKind
    column_name: str
    source: SchemaColumnSource
    expected_type: str | None = None
    actual_type: str | None = None


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
    decrease_policy: str = "deny"

    @property
    def decreases(self) -> bool:
        """Whether this entry lowers any live retention value."""

        return self.direction in (RetentionDirection.DECREASE, RetentionDirection.MIXED)


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
class ModelMigrationPlanEntry:
    """One declared or discovered model migration and its per-run decision."""

    model_name: str
    discovery: MigrationDiscovery
    decision: MigrationDecision
    compatibility: MigrationCompatibility
    origin_model: str | None
    origin: CompiledRelationLocation
    destination: CompiledRelationLocation
    target_name: str | None
    origin_version_hash: str = ""
    origin_is_transient: bool = False
    stage_is_transient: bool | None = None
    transfer: MigrationTransfer | None = None
    transfer_fallback: MigrationTransfer | None = None
    promotion: MigrationPromotion | None = None
    completed_at: datetime | None = None
    compatibility_findings: tuple[str, ...] = ()
    message: str | None = None
    origin_tracked: bool = False
    missing_origin_policy: MissingMigrationOriginPolicy = MissingMigrationOriginPolicy.ALLOW

    @property
    def origin_missing(self) -> bool:
        """Return whether the declared origin was not found in this target."""

        return self.decision == MigrationDecision.ORIGIN_MISSING

    @property
    def origin_hidden(self) -> bool:
        """Return whether the missing origin has build history in this target."""

        return self.origin_missing and self.origin_tracked

    @property
    def storage_transition(self) -> str | None:
        """Return the Snowflake table-type transition label, when both types are known."""

        if self.stage_is_transient is None:
            return None
        labels: tuple[str, str] = ("permanent", "transient")
        return f"{labels[self.origin_is_transient]} -> {labels[self.stage_is_transient]}"

    @property
    def target_label(self) -> str:
        """Return the target name shown in migration text, naming the unnamed target 'default'."""

        return self.target_name or "default"

    @property
    def blocks_build(self) -> bool:
        """Return whether this migration must stop a build before any execution."""

        if self.origin_missing:
            return (
                self.origin_tracked
                or self.missing_origin_policy == MissingMigrationOriginPolicy.DENY
            )
        return self.decision.blocks_build or (
            self.decision.moves_data and self.compatibility == MigrationCompatibility.INCOMPATIBLE
        )


@dataclass(frozen=True)
class OldNameViewPlanEntry:
    """What one build does at the old name of one migrated model."""

    model_name: str
    origin: CompiledRelationLocation
    destination: CompiledRelationLocation
    action: OldNameViewAction
    target_name: str | None
    retention: str | None = None
    expires_at: datetime | None = None
    column_aliases: tuple[tuple[str, str], ...] = ()
    stores_history: bool = False
    migration_event_id: str | None = None
    records_requirement: bool = False
    reason: str | None = None
    grants_copied: int | None = None
    grants_supported: bool = False
    archived: bool = False

    @property
    def runs_steps(self) -> bool:
        """Return whether this build archives the old relation or creates the view."""

        return self.action in (OldNameViewAction.ARCHIVE_AND_VIEW, OldNameViewAction.VIEW_ONLY)


@dataclass(frozen=True)
class OldNameView:
    """One compatibility view recorded at an old name and not recorded as dropped."""

    destination_model: str
    old: CompiledRelationLocation
    new: CompiledRelationLocation
    expires_at: datetime | None
    column_aliases: tuple[tuple[str, str], ...]
    migration_event_id: str
    target_name: str | None
    name_reused_by: str | None = None


@dataclass(frozen=True)
class ColumnMigrationPlanEntry:
    """One declared or detected in-place column rename and its per-run decision."""

    model_name: str
    destination: CompiledRelationLocation
    origin_column: str
    destination_column: str
    discovery: MigrationDiscovery
    decision: ColumnMigrationDecision
    target_name: str | None
    completed_at: datetime | None = None
    message: str | None = None
    missing_origin_policy: MissingMigrationOriginPolicy = MissingMigrationOriginPolicy.ALLOW

    @property
    def origin_missing(self) -> bool:
        """Return whether the declared origin column was not found in this target."""

        return self.decision == ColumnMigrationDecision.SOURCE_MISSING

    @property
    def blocks_build(self) -> bool:
        """Return whether this column migration must stop a build before any execution."""

        if self.origin_missing:
            return self.missing_origin_policy == MissingMigrationOriginPolicy.DENY
        return self.decision.blocks_build


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
    migration_fingerprint: str | None = None
    incremental_strategy: str | None = None
    incremental_mode: str | None = None
    microbatch_strategy: str | None = None
    cursor_watermark_mode: str | None = None
    cursor_column: str | None = None
    cursor_type: str | None = None
    cursor_grain: str | None = None
    cursor_start: str | None = None
    cursor_end: str | None = None
    lookback: str | None = None
    cursor_bounds: CursorBounds | None = None
    empty_cursor_inputs: tuple[str, ...] = ()
    waiting_on_empty_inputs: bool = False
    cursor_input_relations: tuple[CursorInputRelation, ...] = field(default_factory=tuple)
    batch_size: str | None = None
    batch_concurrency: int = 1
    unaccounted_partition_policy: str | None = None
    microbatch_range: CursorBounds | None = None
    microbatch_limit: int | None = None
    declared_microbatch_limit_action: MicrobatchLimitAction | None = None
    microbatch_safety_limit: int | None = None
    microbatch_safety_limit_action: MicrobatchLimitAction | None = None
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
    contract_dynamic_columns: tuple[SchemaDynamicColumnFamily, ...] = field(default_factory=tuple)
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
    changed_functions: tuple[str, ...] = field(default_factory=tuple)
    custom_materialization_name: str | None = None
    custom_config: dict[str, object] = field(default_factory=dict)
    custom_placeholders: dict[str, str] = field(default_factory=dict)
    column_rename_hints: tuple[ColumnRenameHint, ...] = field(default_factory=tuple)


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


@dataclass(frozen=True)
class AuditPlanEntry:
    """Per-audit execution plan entry with resolved SQL and scheduling metadata."""

    key: CompiledObjectKey
    name: str
    definition_name: str
    resolved_sql: str
    unresolved_sql: str
    attachment_kind: AuditAttachmentKind
    severity: AuditSeverity
    requested_run_scope: AuditRunScope
    effective_run_scope: AuditRunScope
    evaluation_mode: AuditEvaluationMode = AuditEvaluationMode.VIOLATIONS
    value_column: str | None = None
    sample_count_column: str | None = None
    sample_unit: str | None = None
    thresholds: MeasurementThresholds | None = None
    minimum_samples: int | None = None
    evidence_resolved_sql: str | None = None
    evidence_unresolved_sql: str | None = None
    evidence_limit: int | None = None
    scope_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    attached_target_kind: AttachedAuditTargetKind | None = None
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    always_run: bool = False
    description: str | None = None
    reads_outside_target_lineage: bool = False


@dataclass(frozen=True)
class ChainStep:
    """One step in a chained test execution sequence."""

    model_name: str
    resolved_sql: str
    expected_cte_sql: str | None = None
    lifted_ctes: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    comparison_body_sql: str | None = None
    expected_columns: tuple[str, ...] | None = None
    expected_lifted_ctes: tuple[tuple[str, str], ...] = field(default_factory=tuple)


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
    mock_ref_names: tuple[str, ...] = field(default_factory=tuple)
    mock_source_names: tuple[str, ...] = field(default_factory=tuple)
    mock_seed_names: tuple[str, ...] = field(default_factory=tuple)
    mock_dbt_ref_names: tuple[str, ...] = field(default_factory=tuple)
    mock_table_function_names: tuple[str, ...] = field(default_factory=tuple)
    chain: tuple[ChainStep, ...] = field(default_factory=tuple)
    assertions: tuple[SqlTestAssertionStep, ...] = field(default_factory=tuple)
    scope_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    function_deps: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    sql_analysis_enabled: bool = True


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
class PlanOutput:
    """Complete execution plan produced by the planner."""

    execution_order: tuple[CompiledObjectKey, ...] = field(default_factory=tuple)
    model_entries: tuple[ModelPlanEntry, ...] = field(default_factory=tuple)
    seed_entries: tuple[SeedPlanEntry, ...] = field(default_factory=tuple)
    source_load_entries: tuple[SourceLoadPlanEntry, ...] = field(default_factory=tuple)
    function_entries: tuple[FunctionPlanEntry, ...] = field(default_factory=tuple)
    audit_entries: tuple[AuditPlanEntry, ...] = field(default_factory=tuple)
    test_entries: tuple[SqlTestPlanEntry, ...] = field(default_factory=tuple)
    available_test_case_names: tuple[str, ...] = field(default_factory=tuple)
    selected_keys: frozenset[CompiledObjectKey] = field(default_factory=frozenset)
    warnings: tuple[PlanWarning, ...] = field(default_factory=tuple)
    retention_entries: tuple[RetentionPlanEntry, ...] = field(default_factory=tuple)
    table_type_entries: tuple[TableTypePlanEntry, ...] = field(default_factory=tuple)
    migration_entries: tuple[ModelMigrationPlanEntry, ...] = field(default_factory=tuple)
    column_migration_entries: tuple[ColumnMigrationPlanEntry, ...] = field(default_factory=tuple)
    old_name_view_entries: tuple[OldNameViewPlanEntry, ...] = field(default_factory=tuple)
    old_name_views: tuple[OldNameView, ...] = field(default_factory=tuple)
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
    python_source_read_map: dict[str, SourceEntry] = field(default_factory=dict)
    hook_functions: tuple[DiscoveredHookFunction, ...] = field(default_factory=tuple)
    enforce_explicit_references: bool = True
    provider_usages: tuple[PlanProviderUsage, ...] = field(default_factory=tuple)
    source_freshness: DirectSourceFreshnessPlanningResult | None = None
    python_identity_fingerprints: dict[tuple[str, str], Fingerprint] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)
    cursor_overrides: CursorOverrides | None = None

    @property
    def python_source_entries(self) -> dict[str, SourceEntry]:
        """Return the source entries Python reads resolve, as a selected SQL read sees them."""

        return self.python_source_read_map or self.source_read_map or self.source_map
