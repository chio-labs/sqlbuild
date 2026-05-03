"""Test helpers for build output formatter tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput, SeedPlanEntry
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus


@dataclass(frozen=True)
class ModelPlanOverride:
    """Override for a model plan entry in output tests."""

    name: str
    materialization_type: MaterializationType = MaterializationType.TABLE
    action: PlanAction = PlanAction.CREATE_TABLE


def build_model_result_fields(
    *,
    name: str,
    status: ExecutionStatus,
    duration_ms: int = 100,
    failed_phase: ExecutionPhase | None = None,
    staging_relation: str | None = None,
    promoted_relation: str | None = None,
    error_message: str | None = None,
    audit_results: tuple[AuditExecutionResult, ...] = (),
    warning_messages: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "model_name": name,
        "status": status,
        "duration_ms": duration_ms,
        "failed_phase": failed_phase,
        "staging_relation": staging_relation,
        "promoted_relation": promoted_relation,
        "error_message": error_message,
        "audit_results": audit_results,
        "warning_messages": warning_messages,
    }


def build_audit_result(
    *,
    name: str,
    outcome: AuditOutcome,
    row_count: int = 0,
    column_name: str | None = None,
    run_scope_phase: AuditRunScope = AuditRunScope.FINAL,
) -> AuditExecutionResult:
    return AuditExecutionResult(
        audit_name=name,
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.WARN if outcome == AuditOutcome.WARN else AuditSeverity.ERROR,
        outcome=outcome,
        row_count=row_count,
        executed_sql="SELECT 1",
        run_scope_phase=run_scope_phase,
        attached_target_name="test_model",
        attached_column_name=column_name,
    )


def build_model_plan_entry(
    *,
    name: str,
    materialization_type: MaterializationType = MaterializationType.TABLE,
    action: PlanAction = PlanAction.CREATE_TABLE,
    incremental_strategy: str | None = None,
) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=materialization_type,
        action=action,
        reason=PlanReason.FIRST_RUN,
        target=CompiledRelationTarget(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        fingerprint_query_sql="SELECT 1",
        resolved_sql="SELECT 1",
        logical_ddl=f"CREATE TABLE main.{name} AS SELECT 1",
        incremental_strategy=incremental_strategy,
    )


def build_seed_plan_entry(*, name: str) -> SeedPlanEntry:
    return SeedPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name=name),
        name=name,
        target=CompiledRelationTarget(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        file_path=Path(f"seeds/{name}.csv"),
        columns=(),
    )


def build_plan_output(
    *,
    model_entries: tuple[ModelPlanEntry, ...] = (),
    seed_entries: tuple[SeedPlanEntry, ...] = (),
) -> PlanOutput:
    return PlanOutput(
        model_entries=model_entries,
        seed_entries=seed_entries,
    )
