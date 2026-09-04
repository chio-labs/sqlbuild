"""Executor run domain models."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import LifeCycleEvent, QueryResult
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    CursorBounds,
    CursorInputRelation,
    FutureCursorSafetyEvidence,
    MaximumStartSafetyEvidence,
    ModelPlanEntry,
)
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.custom.models import MaterializationResult
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.executor.run.types import (
    AuditGateReuseReason,
    ExecutionPhase,
    HookPhase,
    MicrobatchBatchRunner,
    WatermarkResolver,
)
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.microbatches.models import MicrobatchScope
from sqlbuild.microbatches.types import MicrobatchEventStore
from sqlbuild.provider.main.runtime import ProviderContainer, _empty_provider_container
from sqlbuild.spec.contracts.models import FutureCursorsConfig, SourceEntry, StartCursorsConfig
from sqlbuild.spec.contracts.types import MicrobatchLimitAction


@dataclass(frozen=True)
class BatchWindow:
    """One batch window with start (inclusive) and end (exclusive) bounds."""

    start: str
    end: str
    index: int


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


@dataclass(frozen=True)
class RuntimeCursorSpec:
    """Cursor configuration inputs for runtime-owned bound resolution."""

    cursor_column: str
    cursor_type: str | None
    cursor_grain: str | None
    cursor_start: str | None
    cursor_input_relations: tuple[CursorInputRelation, ...]
    cursor_end: str | None = None
    cursor_watermark_mode: str = "all"
    microbatch_strategy: str | None = None
    incremental_strategy: str | None = None
    incremental_mode: str | None = None
    start_cursor_override: str | None = None
    end_cursor_override: str | None = None
    lookback: str | None = None
    backfill_duration: str | None = None
    read_destination_cursor: bool = True
    future_cursor_config: FutureCursorsConfig | None = None
    start_cursor_config: StartCursorsConfig | None = None
    invocation_time: datetime | None = None


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
