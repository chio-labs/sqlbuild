"""Build executor domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    FunctionPlanEntry,
    ModelPlanEntry,
    SeedPlanEntry,
    SourceLoadPlanEntry,
    SqlTestPlanEntry,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.load.models import LoadExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult


@dataclass(frozen=True)
class SeedExecutionResult:
    """Outcome of one seed load."""

    seed_name: str
    status: ExecutionStatus
    duration_ms: int | None = None
    lifecycle_events: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)
    error_code: str | None = None
    error_help: str | None = None
    error_message: str | None = None
    warning_messages: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FunctionExecutionResult:
    """Outcome of one SQL function creation."""

    function_name: str
    status: ExecutionStatus
    function_kind: str
    duration_ms: int | None = None
    error_code: str | None = None
    error_help: str | None = None
    error_message: str | None = None
    warning_messages: tuple[str, ...] = field(default_factory=tuple)
    lifecycle_events: tuple[LifeCycleEvent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BuildIndexes:
    """Precomputed lookup structures for build execution loop."""

    model_entries_by_key: dict[CompiledObjectKey, ModelPlanEntry] = field(default_factory=dict)
    seed_entries_by_key: dict[CompiledObjectKey, SeedPlanEntry] = field(default_factory=dict)
    function_entries_by_key: dict[CompiledObjectKey, FunctionPlanEntry] = field(
        default_factory=dict
    )
    source_load_entries_by_key: dict[CompiledObjectKey, SourceLoadPlanEntry] = field(
        default_factory=dict
    )
    test_entries_by_key: dict[CompiledObjectKey, SqlTestPlanEntry] = field(default_factory=dict)
    source_audits_by_source: dict[str, tuple[AuditPlanEntry, ...]] = field(default_factory=dict)
    model_audits_by_model: dict[str, tuple[AuditPlanEntry, ...]] = field(default_factory=dict)
    end_audits: tuple[AuditPlanEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NodeCompletion:
    """Result of a single node execution passed back from a worker to the scheduler."""

    key: CompiledObjectKey
    result: (
        ModelExecutionResult
        | SeedExecutionResult
        | FunctionExecutionResult
        | SqlTestExecutionResult
        | LoadExecutionResult
    )


@dataclass(frozen=True)
class ExternalSourceLoadResults:
    """Results and scheduler state from pre-connection external source loads."""

    results: tuple[LoadExecutionResult, ...]
    completed_keys: frozenset[CompiledObjectKey]
    failed_keys: frozenset[CompiledObjectKey]


@dataclass(frozen=True)
class BuildExecutionResult:
    """Aggregate outcome of a full build execution."""

    status: BuildStatus
    model_results: tuple[ModelExecutionResult, ...] = field(default_factory=tuple)
    seed_results: tuple[SeedExecutionResult, ...] = field(default_factory=tuple)
    function_results: tuple[FunctionExecutionResult, ...] = field(default_factory=tuple)
    load_results: tuple[LoadExecutionResult, ...] = field(default_factory=tuple)
    test_results: tuple[SqlTestExecutionResult, ...] = field(default_factory=tuple)
    source_audit_results: tuple[AuditExecutionResult, ...] = field(default_factory=tuple)
    end_audit_results: tuple[AuditExecutionResult, ...] = field(default_factory=tuple)
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    warning_count: int = 0
