"""Test helpers for CLI shared helpers tests."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.executor.auditing.models import AuditExecutionResult


def write_spinner_line_and_release(
    *,
    write_spinner_line: Callable[[], None],
    spinner_updates: threading.Semaphore,
) -> None:
    write_spinner_line()
    spinner_updates.release()


def build_audit_result(
    *,
    name: str,
    outcome: AuditOutcome,
    run_scope_phase: AuditRunScope = AuditRunScope.FINAL,
    row_count: int = 0,
    column_name: str | None = None,
    target_name: str | None = "test_model",
    reused: bool = False,
) -> AuditExecutionResult:
    return AuditExecutionResult(
        audit_name=name,
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.ERROR,
        outcome=outcome,
        row_count=row_count,
        executed_sql="SELECT 1",
        run_scope_phase=run_scope_phase,
        attached_target_name=target_name,
        attached_column_name=column_name,
        reused=reused,
    )


def build_progress_snapshot_plan_output(
    *,
    name: str = "customer_snapshot",
    snapshot_strategy: str = "timestamp",
    observed_at_column: str | None = None,
    historical_input: str | None = None,
) -> PlanOutput:
    entry: ModelPlanEntry = ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.SNAPSHOT,
        action=PlanAction.SNAPSHOT,
        reason=PlanReason.FIRST_RUN,
        destination=CompiledRelationLocation(
            database=None,
            schema="main",
            name=name,
            qualified_name=f"main.{name}",
        ),
        fingerprint_query_sql="SELECT 1 AS id",
        resolved_sql="SELECT 1 AS id",
        logical_ddl=f"CREATE TABLE main.{name} AS SELECT 1 AS id",
        snapshot_strategy=snapshot_strategy,
        observed_at_column=observed_at_column,
        historical_input=historical_input,
    )
    return PlanOutput(
        execution_order=(entry.key,),
        model_entries=(entry,),
        selected_keys=frozenset((entry.key,)),
    )
