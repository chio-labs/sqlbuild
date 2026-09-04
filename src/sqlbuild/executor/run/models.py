"""Executor run domain models."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import LifeCycleEvent, QueryResult
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    CursorBounds,
    Duration,
    FutureCursorSafetyEvidence,
    MaximumStartSafetyEvidence,
    ModelPlanEntry,
)
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.cursor_algebra.exceptions import CursorAlgebraError
from sqlbuild.cursor_algebra.main.compare import compare
from sqlbuild.cursor_algebra.main.parse import parse
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import BoundSentinel, CursorScalar
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.custom.models import MaterializationResult
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.executor.run.types import (
    AuditGateReuseReason,
    ExecutionPhase,
    HookPhase,
    MicrobatchBatchRunner,
    RuntimeCursorWatermarkMode,
    WatermarkResolver,
)
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.microbatches.models import MicrobatchScope
from sqlbuild.microbatches.types import MicrobatchEventStore
from sqlbuild.provider.main.runtime import ProviderContainer, _empty_provider_container
from sqlbuild.spec.contracts.models import FutureCursorsConfig, SourceEntry, StartCursorsConfig
from sqlbuild.spec.contracts.types import MicrobatchLimitAction


@dataclass(frozen=True, kw_only=True, init=False)
class BatchWindow:
    """One batch window with start (inclusive) and end (exclusive) bounds."""

    start: CursorScalar
    end: CursorScalar
    index: int

    def __init__(self, *, start: CursorScalar | str, end: CursorScalar | str, index: int) -> None:
        bounds: CursorBounds = CursorBounds(start=start, end=end)
        if not isinstance(
            bounds.start, TimestampValue | DateValue | IntegerValue
        ) or not isinstance(bounds.end, TimestampValue | DateValue | IntegerValue):
            raise CursorAlgebraError("batch windows require concrete cursor scalars")
        if compare(left=bounds.start, right=bounds.end) > 0:
            raise CursorAlgebraError("batch window start must not exceed end")
        object.__setattr__(self, "start", bounds.start)
        object.__setattr__(self, "end", bounds.end)
        object.__setattr__(self, "index", index)


@dataclass(frozen=True)
class HookRelation:
    name: str
    schema: str | None
    database: str | None
    qualified: str


@dataclass(frozen=True)
class HookContext:
    model_name: str
    phase: HookPhase
    hook_name: str
    hook_index: int
    run_id: str
    target: str | None
    vars: Mapping[str, object]
    destination: HookRelation
    adapter_name: str
    adapter: BaseAdapter = field(repr=False)
    connection: Any = field(repr=False)
    statement_recorder: StatementRecorder = field(repr=False)
    providers: ProviderContainer = field(default_factory=_empty_provider_container, repr=False)

    def execute_sql(self, sql: str) -> None:
        self.statement_recorder.record(sql)
        self.adapter.execute(connection=self.connection, sql=sql)

    def query(self, sql: str) -> list[tuple[object, ...]]:
        self.statement_recorder.record(sql)
        result: QueryResult = self.adapter.query(connection=self.connection, sql=sql, limit=None)
        return list(result.rows)

    def log(self, message: str) -> None:
        self.statement_recorder.log(message)

    def skip(self, *, reason: str, mode: SkipMode | str = SkipMode.SOFT) -> HookSkipResult:
        """Return a skip signal for the current hook."""

        return HookSkipResult(reason=reason, mode=SkipMode(mode))


@dataclass(frozen=True)
class HookSkipResult:
    """User-facing skip signal returned by a Python hook."""

    reason: str
    mode: SkipMode = SkipMode.SOFT


@dataclass(frozen=True)
class HookExecutionResult:
    phase: HookPhase
    index: int
    hook_type: str
    label: str
    status: ExecutionStatus
    skip_mode: SkipMode | None = None
    skip_reason: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ModelExecutionResult:
    """Outcome of one model materialization lifecycle."""

    model_name: str
    status: ExecutionStatus
    failed_phase: ExecutionPhase | None = None
    staging_relation: str | None = None
    promoted_relation: str | None = None
    duration_ms: int | None = None
    batch_count: int | None = None
    batch_size: str | None = None
    rows_affected: int | None = None
    cursor_range_start: str | None = None
    cursor_range_end: str | None = None
    cursor_type: str | None = None
    cursor_grain: str | None = None
    future_cursor_safety: FutureCursorSafetyEvidence | None = None
    maximum_start_safety: MaximumStartSafetyEvidence | None = None
    audit_results: tuple[AuditExecutionResult, ...] = field(default_factory=tuple)
    warning_messages: tuple[str, ...] = field(default_factory=tuple)
    lifecycle_events: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)
    hook_results: tuple[HookExecutionResult, ...] = field(default_factory=tuple)
    skip_mode: SkipMode | None = None
    skip_reason: str | None = None
    error_code: str | None = None
    error_help: str | None = None
    error_message: str | None = None
    microbatch_run_type: str | None = None
    microbatch_strategy: str | None = None
    microbatch_plan_reason: str | None = None
    microbatch_recovery_batch_count: int = 0
    microbatch_known_gap_count: int = 0
    microbatch_unaccounted_interval_count: int = 0
    microbatch_synthetic_completion_count: int = 0
    microbatch_unknown_fingerprint_count: int = 0
    microbatch_contiguous_frontier: str | None = None
    microbatch_unaccounted_partition_policy: str | None = None
    microbatch_replay_requirement_id: str | None = None
    microbatch_required_model_version_hash: str | None = None
    microbatch_physical_generation_id: str | None = None
    microbatch_concurrent_enabled: bool = False
    microbatch_batch_concurrency: int = 1
    microbatch_global_concurrency: int = 1
    microbatch_replay_requirement_state: str | None = None
    microbatch_accounting_intervals: tuple[MicrobatchAccountingInterval, ...] = field(
        default_factory=tuple
    )
    microbatch_applied_intervals: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    microbatch_limit: int | None = None
    microbatch_limit_count: int | None = None
    microbatch_limit_action: MicrobatchLimitAction | None = None
    microbatch_limit_warning: str | None = None


@dataclass(frozen=True)
class MicrobatchAccountingInterval:
    """Runtime interval accounting exposed to JSON/node-result consumers."""

    partition_start: str
    partition_end: str
    accounting_status: str
    fingerprint_status: str
    model_version_hash: str | None = None
    completion_type: str | None = None
    event_id: str | None = None


@dataclass(frozen=True)
class FinalAuditRun:
    """Final-audit outcomes for one model before promotion."""

    results: tuple[AuditExecutionResult, ...]
    has_error: bool


@dataclass(frozen=True)
class AuditGateReuseDecision:
    """Conservative same-target audit gate proof reuse decision."""

    reusable: bool
    reason: AuditGateReuseReason
    reusable_binding_keys: tuple[str, ...] = ()
    missing_binding_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelMaterializationContext:
    """Shared runtime inputs for one model's materialization lifecycle."""

    entry: ModelPlanEntry
    adapter: BaseAdapter
    connection: Any
    model_locations: dict[str, CompiledRelationLocation]
    seed_locations: dict[str, CompiledRelationLocation]
    source_map: dict[str, SourceEntry]
    model_audits: tuple[AuditPlanEntry, ...]
    run_id: str
    query_change_tracking: bool
    schema_prepared: bool = False
    hook_functions: tuple[DiscoveredHookFunction, ...] = ()
    effective_target_name: str | None = None
    effective_vars: Mapping[str, object] | None = None
    providers: ProviderContainer | None = None
    python_identity_recorder: PythonIdentityRecorder | None = None
    microbatch_event_store: MicrobatchEventStore | None = None
    microbatch_event_store_resolver: Callable[[Any], MicrobatchEventStore] | None = None
    microbatch_scope: MicrobatchScope | None = None
    microbatch_model_version_hash: str | None = None
    microbatch_unaccounted_partition_policy: str = "synthesize"
    microbatch_lease_check: Callable[[], None] | None = None
    microbatch_global_concurrency: int = 1
    microbatch_batch_runner: MicrobatchBatchRunner | None = None
    watermark_resolver: WatermarkResolver | None = None


@dataclass(frozen=True, kw_only=True, init=False)
class RuntimeCursorInputRelation:
    """Typed cursor input relation consumed by runtime bound resolution."""

    relation: str
    cursor_column: str
    cursor_grain: CursorGrain | None = None
    is_model_backed: bool = False
    is_runtime_produced: bool = False
    terminal_cursor_start: CursorScalar | None = None
    terminal_cursor_end: CursorScalar | None = None

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
    ) -> None:
        object.__setattr__(self, "relation", relation)
        object.__setattr__(self, "cursor_column", cursor_column)
        object.__setattr__(
            self,
            "cursor_grain",
            CursorGrain(cursor_grain) if cursor_grain is not None else None,
        )
        object.__setattr__(self, "is_model_backed", is_model_backed)
        object.__setattr__(self, "is_runtime_produced", is_runtime_produced)
        object.__setattr__(
            self,
            "terminal_cursor_start",
            self._optional_inferred_scalar(value=terminal_cursor_start),
        )
        object.__setattr__(
            self,
            "terminal_cursor_end",
            self._optional_inferred_scalar(value=terminal_cursor_end),
        )

    @staticmethod
    def _optional_inferred_scalar(*, value: CursorScalar | str | None) -> CursorScalar | None:
        if value is None or isinstance(value, TimestampValue | DateValue | IntegerValue):
            return value
        bounds: CursorBounds = CursorBounds(start=value, end=value)
        if isinstance(bounds.start, BoundSentinel):
            raise CursorAlgebraError("runtime cursor inputs require concrete terminal bounds")
        return bounds.start

    @property
    def is_runtime_owned(self) -> bool:
        return self.is_runtime_produced


@dataclass(frozen=True, kw_only=True, init=False)
class RuntimeCursorSpec:
    """Cursor configuration inputs for runtime-owned bound resolution."""

    cursor_column: str
    cursor_type: CursorType | None
    cursor_grain: CursorGrain | None
    cursor_start: CursorScalar | None
    cursor_input_relations: tuple[RuntimeCursorInputRelation, ...]
    cursor_end: CursorScalar | None = None
    cursor_watermark_mode: RuntimeCursorWatermarkMode = RuntimeCursorWatermarkMode.ALL
    microbatch_strategy: str | None = None
    incremental_strategy: str | None = None
    incremental_mode: str | None = None
    start_cursor_override: CursorScalar | None = None
    end_cursor_override: CursorScalar | None = None
    lookback: Duration | None = None
    backfill_duration: Duration | None = None
    read_destination_cursor: bool = True
    future_cursor_config: FutureCursorsConfig | None = None
    start_cursor_config: StartCursorsConfig | None = None
    invocation_time: datetime | None = None

    def __init__(self, **values: Any) -> None:
        defaults: dict[str, object] = {
            "cursor_end": None,
            "cursor_watermark_mode": RuntimeCursorWatermarkMode.ALL,
            "microbatch_strategy": None,
            "incremental_strategy": None,
            "incremental_mode": None,
            "start_cursor_override": None,
            "end_cursor_override": None,
            "lookback": None,
            "backfill_duration": None,
            "read_destination_cursor": True,
            "future_cursor_config": None,
            "start_cursor_config": None,
            "invocation_time": None,
        }
        defaults.update(values)
        cursor_type_raw: object = defaults["cursor_type"]
        cursor_type: CursorType | None = (
            CursorType(str(cursor_type_raw)) if cursor_type_raw is not None else None
        )
        defaults["cursor_type"] = cursor_type
        cursor_grain_raw: object = defaults["cursor_grain"]
        defaults["cursor_grain"] = (
            CursorGrain(str(cursor_grain_raw)) if cursor_grain_raw is not None else None
        )
        defaults["cursor_watermark_mode"] = RuntimeCursorWatermarkMode(
            str(defaults["cursor_watermark_mode"])
        )
        for field_name in (
            "cursor_start",
            "cursor_end",
            "start_cursor_override",
            "end_cursor_override",
        ):
            raw: object | None = defaults[field_name]
            defaults[field_name] = (
                parse(raw=raw, cursor_type=cursor_type or CursorType.TIMESTAMP)
                if raw is not None
                and not isinstance(raw, TimestampValue | DateValue | IntegerValue)
                else raw
            )
        relations: tuple[RuntimeCursorInputRelation, ...] = cast(
            tuple[RuntimeCursorInputRelation, ...], defaults["cursor_input_relations"]
        )
        defaults["cursor_input_relations"] = tuple(
            RuntimeCursorInputRelation(
                relation=relation.relation,
                cursor_column=relation.cursor_column,
                cursor_grain=(
                    CursorGrain(str(relation.cursor_grain))
                    if relation.cursor_grain is not None
                    else None
                ),
                is_model_backed=relation.is_model_backed,
                is_runtime_produced=relation.is_runtime_produced,
                terminal_cursor_start=(
                    parse(raw=relation.terminal_cursor_start, cursor_type=cursor_type)
                    if relation.terminal_cursor_start is not None
                    and not isinstance(
                        relation.terminal_cursor_start,
                        TimestampValue | DateValue | IntegerValue,
                    )
                    and cursor_type is not None
                    else relation.terminal_cursor_start
                ),
                terminal_cursor_end=(
                    parse(raw=relation.terminal_cursor_end, cursor_type=cursor_type)
                    if relation.terminal_cursor_end is not None
                    and not isinstance(
                        relation.terminal_cursor_end,
                        TimestampValue | DateValue | IntegerValue,
                    )
                    and cursor_type is not None
                    else relation.terminal_cursor_end
                ),
            )
            for relation in relations
        )
        for field_name in ("lookback", "backfill_duration"):
            raw_duration: object | None = defaults[field_name]
            defaults[field_name] = (
                Duration.parse(str(raw_duration))
                if raw_duration is not None and not isinstance(raw_duration, Duration)
                else raw_duration
            )
        for field_name in self.__dataclass_fields__:
            object.__setattr__(self, field_name, defaults[field_name])


@dataclass(frozen=True)
class HookRunContext:
    """Model-scoped runtime inputs shared by lifecycle hook execution."""

    model_name: str | None = None
    destination: CompiledRelationLocation | None = None
    run_id: str = ""
    target: str | None = None
    effective_vars: Mapping[str, object] | None = None
    statement_recorder: StatementRecorder | None = None
    providers: ProviderContainer | None = None
    python_identity_recorder: PythonIdentityRecorder | None = None


@dataclass(frozen=True)
class PostHookPhaseOutcome:
    """Post-hook phase result: a skip request or an early failure result."""

    skipped: bool = False
    failure: ModelExecutionResult | None = None


@dataclass(frozen=True)
class CustomLifecycleState:
    """In-flight accumulators for one custom materialization lifecycle."""

    warnings: list[str]
    audit_results: list[AuditExecutionResult]
    hook_results: list[HookExecutionResult]
    statement_recorder: StatementRecorder


@dataclass(frozen=True)
class CustomMaterializationSetup:
    """Configuration values resolved after custom pre-hooks complete."""

    destination_qualified: str
    config: dict[str, Any]
    placeholders: dict[str, str]


@dataclass(frozen=True)
class CustomMaterializationPhaseOutcome:
    """Custom materialization result or its early execution failure."""

    result: MaterializationResult | None = None
    failure: ModelExecutionResult | None = None


@dataclass(frozen=True)
class CustomLifecyclePhaseOutcome:
    """Updated custom lifecycle state and any early phase failure."""

    state: CustomLifecycleState
    failure: ModelExecutionResult | None = None


@dataclass(frozen=True)
class MicrobatchTargets:
    """Resolved target and delta relation identifiers for one microbatch run."""

    target_database: str | None
    target_schema: str | None
    target_table: str
    target_qualified: str
    delta_table: str
    delta_qualified: str


@dataclass(frozen=True)
class FullRefreshRelations:
    """Deterministic live, rebuild, and previous relation names."""

    target_name: str
    target_qualified: str
    rebuild_name: str
    rebuild_qualified: str
    previous_name: str
    previous_qualified: str


@dataclass(frozen=True)
class MicrobatchLifecycleState:
    """In-flight accumulators for one microbatch lifecycle."""

    warnings: list[str]
    audit_results: list[AuditExecutionResult]
    hook_results: list[HookExecutionResult]
    statement_recorder: StatementRecorder


@dataclass(frozen=True)
class MicrobatchSchemaPhaseOutcome:
    """Schema-check state and any early failure from the first eligible batch."""

    state: MicrobatchLifecycleState
    schema_checked: bool
    failure: ModelExecutionResult | None = None


@dataclass(frozen=True)
class MicrobatchPhaseOutcome:
    """Updated microbatch lifecycle state and any early phase failure."""

    state: MicrobatchLifecycleState
    failure: ModelExecutionResult | None = None
    completed_batches: int = 0
    rows_affected: int | None = None
    applied_intervals: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TableCursorResolution:
    """Runtime cursor outcome resolved before table pre-hooks."""

    resolved_sql: str
    bounds: CursorBounds | None
    warning: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class TableTargets:
    """Resolved destination and staging identifiers for one table model."""

    target_qualified: str
    target_database: str | None
    target_schema: str | None
    target_table: str
    staging_qualified: str
    staging_table: str


@dataclass(frozen=True)
class TableLifecycleState:
    """In-flight accumulators and resolved SQL for one table lifecycle run."""

    warnings: list[str]
    audit_results: list[AuditExecutionResult]
    statement_recorder: StatementRecorder
    hook_results: list[HookExecutionResult]
    resolved_sql: str
