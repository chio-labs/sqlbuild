"""Executor run domain models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.models import LifeCycleEvent, QueryResult
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import AuditPlanEntry, CursorInputRelation, ModelPlanEntry
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.python_nodes.types import PythonIdentityRecorder
from sqlbuild.executor.run.types import AuditGateReuseReason, HookPhase
from sqlbuild.executor.types import ExecutionPhase, ExecutionStatus
from sqlbuild.provider.main.runtime import ProviderContainer, _empty_provider_container
from sqlbuild.spec.contracts.models import SourceEntry


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

    def skip(self, reason: str, *, mode: SkipMode | str = SkipMode.SOFT) -> HookSkipResult:
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
    audit_results: tuple[AuditExecutionResult, ...] = field(default_factory=tuple)
    warning_messages: tuple[str, ...] = field(default_factory=tuple)
    lifecycle_events: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)
    hook_results: tuple[HookExecutionResult, ...] = field(default_factory=tuple)
    skip_mode: SkipMode | None = None
    skip_reason: str | None = None
    error_code: str | None = None
    error_help: str | None = None
    error_message: str | None = None


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
    hook_functions: tuple[DiscoveredHookFunction, ...] = ()
    effective_target_name: str | None = None
    effective_vars: Mapping[str, object] | None = None
    providers: ProviderContainer | None = None
    python_identity_recorder: PythonIdentityRecorder | None = None


@dataclass(frozen=True)
class RuntimeCursorSpec:
    """Cursor configuration inputs for runtime-owned bound resolution."""

    cursor_column: str
    cursor_type: str | None
    cursor_grain: str | None
    cursor_start: str | None
    cursor_input_relations: tuple[CursorInputRelation, ...]


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
