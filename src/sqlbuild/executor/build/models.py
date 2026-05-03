"""Build executor domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    ModelPlanEntry,
    SeedPlanEntry,
    SqlTestPlanEntry,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.executor.testing.models import SqlTestExecutionResult


@dataclass(frozen=True)
class SeedExecutionResult:
    """Outcome of one seed load."""

    seed_name: str
    status: ExecutionStatus
    error_message: str | None = None


@dataclass(frozen=True)
class BuildIndexes:
    """Precomputed lookup structures for build execution loop."""

    model_entries_by_key: dict[CompiledObjectKey, ModelPlanEntry] = field(default_factory=dict)
    seed_entries_by_key: dict[CompiledObjectKey, SeedPlanEntry] = field(default_factory=dict)
    test_entries_by_key: dict[CompiledObjectKey, SqlTestPlanEntry] = field(default_factory=dict)
    source_audits_by_source: dict[str, tuple[AuditPlanEntry, ...]] = field(default_factory=dict)
    model_audits_by_model: dict[str, tuple[AuditPlanEntry, ...]] = field(default_factory=dict)
    end_audits: tuple[AuditPlanEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BuildExecutionResult:
    """Aggregate outcome of a full build execution."""

    status: BuildStatus
    model_results: tuple[ModelExecutionResult, ...] = field(default_factory=tuple)
    seed_results: tuple[SeedExecutionResult, ...] = field(default_factory=tuple)
    test_results: tuple[SqlTestExecutionResult, ...] = field(default_factory=tuple)
    source_audit_results: tuple[AuditExecutionResult, ...] = field(default_factory=tuple)
    end_audit_results: tuple[AuditExecutionResult, ...] = field(default_factory=tuple)
    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    warning_count: int = 0
