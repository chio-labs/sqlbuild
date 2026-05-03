"""Test helpers for plan formatter tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    ModelPlanEntry,
    PlanOutput,
    PlanWarning,
    SchemaFinding,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
    SchemaChangeKind,
    SchemaColumnSource,
    WarningSeverity,
)


def build_model_entry(
    *,
    name: str,
    action: PlanAction = PlanAction.CREATE_TABLE,
    reason: PlanReason = PlanReason.FIRST_RUN,
    backfill_action: BackfillAction = BackfillAction.FULL,
    backfill_duration: str | None = None,
    previous_query_sql: str | None = None,
    cursor_column: str | None = None,
    schema_findings: tuple[SchemaFinding, ...] = (),
) -> ModelPlanEntry:
    """Build a minimal ModelPlanEntry for formatter tests."""

    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.TABLE,
        action=action,
        reason=reason,
        target=CompiledRelationTarget(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        resolved_sql=f"SELECT * FROM {name}",
        logical_ddl=f"CREATE TABLE main.{name} AS (SELECT * FROM {name})",
        cursor_column=cursor_column,
        previous_query_sql=previous_query_sql,
        schema_findings=schema_findings,
        backfill=BackfillResult(action=backfill_action, duration=backfill_duration),
    )


def build_plan_output(
    *,
    model_entries: tuple[ModelPlanEntry, ...] = (),
    warnings: tuple[PlanWarning, ...] = (),
) -> PlanOutput:
    """Build a minimal PlanOutput for formatter tests."""

    selected_keys: frozenset[CompiledObjectKey] = frozenset(e.key for e in model_entries)
    return PlanOutput(
        execution_order=tuple(e.key for e in model_entries),
        model_entries=model_entries,
        selected_keys=selected_keys,
        warnings=warnings,
    )


def build_warning(
    *,
    model_name: str,
    message: str,
    severity: WarningSeverity = WarningSeverity.WARNING,
) -> PlanWarning:
    """Build a PlanWarning for formatter tests."""

    return PlanWarning(model_name=model_name, severity=severity, message=message)


def build_schema_finding(
    *,
    kind: SchemaChangeKind,
    column_name: str,
    expected_type: str | None = None,
    actual_type: str | None = None,
) -> SchemaFinding:
    """Build a SchemaFinding for formatter tests."""

    return SchemaFinding(
        kind=kind,
        column_name=column_name,
        source=SchemaColumnSource.YML,
        expected_type=expected_type,
        actual_type=actual_type,
    )
