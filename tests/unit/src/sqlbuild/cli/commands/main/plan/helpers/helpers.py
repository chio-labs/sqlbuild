"""Test helpers for plan formatter tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationDestination,
)
from sqlbuild.compiler.compile.types import CompiledResourceType, FunctionLanguage
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CascadeResult,
    CursorBounds,
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    PlanWarning,
    SchemaFinding,
    SeedPlanEntry,
    SourceLoadPlanEntry,
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
from sqlbuild.spec.models.schema import SeedCsvSettings
from sqlbuild.spec.models.types import SourceWriteStrategy


def build_model_entry(
    *,
    name: str,
    action: PlanAction = PlanAction.CREATE_TABLE,
    reason: PlanReason = PlanReason.FIRST_RUN,
    materialization_type: MaterializationType = MaterializationType.TABLE,
    backfill_action: BackfillAction = BackfillAction.FULL,
    backfill_duration: str | None = None,
    previous_query_sql: str | None = None,
    fingerprint_metadata_json: str | None = None,
    previous_metadata_json: str | None = None,
    cursor_column: str | None = None,
    cursor_type: str | None = None,
    cursor_bounds: CursorBounds | None = None,
    incremental_strategy: str | None = None,
    incremental_mode: str | None = None,
    snapshot_strategy: str | None = None,
    observed_at_column: str | None = None,
    historical_input: str | None = None,
    schema_findings: tuple[SchemaFinding, ...] = (),
    cascade: CascadeResult | None = None,
    custom_materialization_name: str | None = None,
) -> ModelPlanEntry:
    """Build a minimal ModelPlanEntry for formatter tests."""

    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=materialization_type,
        action=action,
        reason=reason,
        target=CompiledRelationDestination(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        fingerprint_query_sql=f"SELECT * FROM {name}",
        resolved_sql=f"SELECT * FROM {name}",
        logical_ddl=f"CREATE TABLE main.{name} AS (SELECT * FROM {name})",
        incremental_strategy=incremental_strategy,
        incremental_mode=incremental_mode,
        snapshot_strategy=snapshot_strategy,
        observed_at_column=observed_at_column,
        historical_input=historical_input,
        cursor_column=cursor_column,
        cursor_type=cursor_type,
        cursor_bounds=cursor_bounds,
        previous_query_sql=previous_query_sql,
        fingerprint_metadata_json=fingerprint_metadata_json,
        previous_metadata_json=previous_metadata_json,
        schema_findings=schema_findings,
        backfill=BackfillResult(action=backfill_action, duration=backfill_duration),
        cascade=cascade,
        custom_materialization_name=custom_materialization_name,
    )


def build_plan_output(
    *,
    model_entries: tuple[ModelPlanEntry, ...] = (),
    seed_entries: tuple[SeedPlanEntry, ...] = (),
    function_entries: tuple[FunctionPlanEntry, ...] = (),
    source_load_entries: tuple[SourceLoadPlanEntry, ...] = (),
    warnings: tuple[PlanWarning, ...] = (),
    metadata: dict[str, object] | None = None,
) -> PlanOutput:
    """Build a minimal PlanOutput for formatter tests."""

    selected_keys: frozenset[CompiledObjectKey] = frozenset(
        e.key for e in (*model_entries, *seed_entries, *function_entries)
    )
    return PlanOutput(
        execution_order=tuple(e.key for e in (*function_entries, *model_entries, *seed_entries)),
        model_entries=model_entries,
        seed_entries=seed_entries,
        function_entries=function_entries,
        source_load_entries=source_load_entries,
        selected_keys=selected_keys,
        warnings=warnings,
        metadata={} if metadata is None else metadata,
    )


def build_source_load_entry(
    *,
    name: str,
    write_strategy: SourceWriteStrategy | None = SourceWriteStrategy.TABLE,
    cursor_column: str | None = None,
    unique_key: tuple[str, ...] = (),
    is_reload: bool = False,
    integration_kind: str | None = None,
) -> SourceLoadPlanEntry:
    """Build a minimal SourceLoadPlanEntry for formatter tests."""

    return SourceLoadPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name),
        name=name,
        loader=f"{name}_loader",
        target=name,
        write_strategy=write_strategy,
        cursor_column=cursor_column,
        unique_key=unique_key,
        is_reload=is_reload,
        integration_kind=integration_kind,
    )


def build_seed_entry(*, name: str) -> SeedPlanEntry:
    """Build a minimal SeedPlanEntry for formatter tests."""

    return SeedPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name=name),
        name=name,
        target=CompiledRelationDestination(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        file_path=Path(f"seeds/{name}.csv"),
        columns=(),
        csv_settings=SeedCsvSettings(),
    )


def build_function_entry(
    *,
    name: str,
    language: FunctionLanguage = FunctionLanguage.SQL,
    reason: PlanReason = PlanReason.NO_CHANGE,
    backfill_action: BackfillAction = BackfillAction.WARN_ONLY,
    backfill_duration: str | None = None,
    previous_query_sql: str | None = None,
) -> FunctionPlanEntry:
    """Build a minimal FunctionPlanEntry for formatter tests."""

    return FunctionPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.FUNCTION, name=name),
        name=name,
        relative_path=Path(f"functions/{language.value}/{name}.sql"),
        target=CompiledRelationDestination(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        fingerprint_target=CompiledRelationDestination(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        arguments=(),
        returns="BOOLEAN",
        body_sql="return True",
        fingerprint_query_sql="return True",
        language=language,
        previous_query_sql=previous_query_sql,
        reason=reason,
        backfill=BackfillResult(action=backfill_action, duration=backfill_duration),
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
