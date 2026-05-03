"""Test helpers for plan formatter tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CascadeResult,
    CursorBounds,
    ModelPlanEntry,
    PlanOutput,
    PlanWarning,
    SchemaFinding,
    SeedPlanEntry,
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
    materialization_type: MaterializationType = MaterializationType.TABLE,
    backfill_action: BackfillAction = BackfillAction.FULL,
    backfill_duration: str | None = None,
    previous_query_sql: str | None = None,
    cursor_column: str | None = None,
    cursor_type: str | None = None,
    cursor_bounds: CursorBounds | None = None,
    incremental_strategy: str | None = None,
    incremental_mode: str | None = None,
    schema_findings: tuple[SchemaFinding, ...] = (),
    cascade: CascadeResult | None = None,
) -> ModelPlanEntry:
    """Build a minimal ModelPlanEntry for formatter tests."""

    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=materialization_type,
        action=action,
        reason=reason,
        target=CompiledRelationTarget(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        resolved_sql=f"SELECT * FROM {name}",
        logical_ddl=f"CREATE TABLE main.{name} AS (SELECT * FROM {name})",
        incremental_strategy=incremental_strategy,
        incremental_mode=incremental_mode,
        cursor_column=cursor_column,
        cursor_type=cursor_type,
        cursor_bounds=cursor_bounds,
        previous_query_sql=previous_query_sql,
        schema_findings=schema_findings,
        backfill=BackfillResult(action=backfill_action, duration=backfill_duration),
        cascade=cascade,
    )


def build_plan_output(
    *,
    model_entries: tuple[ModelPlanEntry, ...] = (),
    seed_entries: tuple[SeedPlanEntry, ...] = (),
    warnings: tuple[PlanWarning, ...] = (),
) -> PlanOutput:
    """Build a minimal PlanOutput for formatter tests."""

    selected_keys: frozenset[CompiledObjectKey] = frozenset(e.key for e in model_entries)
    return PlanOutput(
        execution_order=tuple(e.key for e in model_entries),
        model_entries=model_entries,
        seed_entries=seed_entries,
        selected_keys=selected_keys,
        warnings=warnings,
    )


def build_seed_entry(*, name: str) -> SeedPlanEntry:
    """Build a minimal SeedPlanEntry for formatter tests."""

    return SeedPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name=name),
        name=name,
        target=CompiledRelationTarget(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        file_path=Path(f"seeds/{name}.csv"),
        columns=(),
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
