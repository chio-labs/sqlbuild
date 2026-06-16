"""Executor run domain models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import LifeCycleEvent, QueryResult, StatementRecorder
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.types import AuditGateReuseReason, HookPhase
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.provider.main.runtime import ProviderContainer, _empty_provider_container


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
        self.adapter.execute(self.connection, sql)

    def query(self, sql: str) -> list[tuple[object, ...]]:
        self.statement_recorder.record(sql)
        result: QueryResult = self.adapter.query(self.connection, sql, limit=None)
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
class AuditGateReuseDecision:
    """Conservative same-target audit gate proof reuse decision."""

    reusable: bool
    reason: AuditGateReuseReason
    reusable_binding_keys: tuple[str, ...] = ()
    missing_binding_keys: tuple[str, ...] = ()
