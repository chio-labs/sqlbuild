"""Warehouse inspection and adapter boundaries for native model migration planning."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild._native import (
    manual_migration_requests as manual_migration_requests,
)
from sqlbuild._native import (
    plan_model_migrations as plan_model_migrations,
)
from sqlbuild.adapter.contract.models import MigrationStagePlan, RelationInfo
from sqlbuild.adapter.contract.types import BuiltinAdapter, MigrationTransfer
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledModelView
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.migrations.types import (
    MigrationDecision,
    MigrationPromotion,
)
from sqlbuild.compiler.planner._helpers.planning.full_refresh import (
    effectively_full_refreshed_model_names,
)
from sqlbuild.compiler.planner._helpers.planning.retention import effective_target_config
from sqlbuild.compiler.planner._helpers.warehouse.snapshot import (
    gather_redirected_cursor_snapshots,
)
from sqlbuild.compiler.planner.classes.migration_state_inspection import MigrationStateInspection
from sqlbuild.compiler.planner.constants import QUALIFIED_RELATION_MAX_PARTS
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    CursorSnapshotScope,
    DeferralInputs,
    ModelCursorSnapshot,
    ModelMigrationPlanEntry,
    ModelMigrationRequest,
    PlannerOverrides,
    PlannerRuntime,
    PlannerScope,
)
from sqlbuild.spec.contracts.types import MissingMigrationOriginPolicy, TableType


def planning_database(*, runtime: PlannerRuntime) -> str | None:
    """Return the single database that direct planning inspects for migration state."""

    return next(
        (
            model.destination.database
            for model in runtime.project.models
            if model.destination.database is not None
        ),
        runtime.project.effective_target_database,
    )


def missing_origin_policy(*, runtime: PlannerRuntime) -> MissingMigrationOriginPolicy:
    """Return how the effective target treats a declared migration origin it cannot find."""

    return effective_target_config(runtime=runtime).missing_migration_origin


def project_schemas(*, runtime: PlannerRuntime) -> set[str]:
    """Return every destination schema owned by project models."""

    return {
        model.destination.schema
        for model in runtime.project.models
        if model.destination.schema is not None
    }


def _require_same_database(
    *, state: MigrationStateInspection, location: CompiledRelationLocation
) -> None:
    if (
        location.database is None
        or state.database is None
        or location.database.lower() == state.database.lower()
    ):
        return
    raise PlannerInputError(
        f"migration origin {location.qualified_name or location.name} is in database "
        f"'{location.database}', but direct planning inspects '{state.database}'; "
        "cross-database migrations are not supported"
    )


def _resolve_origin(
    *, request: ModelMigrationRequest, runtime: PlannerRuntime, state: MigrationStateInspection
) -> tuple[CompiledRelationLocation, str | None]:
    if request.origin_location is not None:
        return request.origin_location, request.origin_model
    raw: str = request.raw_origin or ""
    destination: CompiledRelationLocation = request.model.destination
    parts: list[str] = [part.strip().strip('"`') for part in raw.split(".")]
    if any(not part for part in parts) or len(parts) > QUALIFIED_RELATION_MAX_PARTS:
        raise PlannerInputError(
            f"model '{request.model.name}': migrate_from '{raw}' is not a model name or a "
            "qualified relation"
        )
    if len(parts) == 1:
        return _resolve_named_origin(
            name=parts[0], destination=destination, runtime=runtime, state=state
        )
    database: str | None = (
        parts[0] if len(parts) == QUALIFIED_RELATION_MAX_PARTS else destination.database
    )
    schema: str = parts[-2]
    return (
        _location(runtime=runtime, database=database, schema=schema, name=parts[-1]),
        None,
    )


def _resolve_named_origin(
    *,
    name: str,
    destination: CompiledRelationLocation,
    runtime: PlannerRuntime,
    state: MigrationStateInspection,
) -> tuple[CompiledRelationLocation, str | None]:
    project_model: CompiledModelView | None = next(
        (model for model in runtime.project.models if model.name == name), None
    )
    if project_model is not None:
        return project_model.destination, name
    fingerprint: Fingerprint | None = state.named_fingerprint(model_name=name)
    if fingerprint is not None and fingerprint.target_name is not None:
        return (
            _location(
                runtime=runtime,
                database=fingerprint.target_database,
                schema=fingerprint.target_schema,
                name=fingerprint.target_name,
            ),
            name,
        )
    return (
        _location(
            runtime=runtime, database=destination.database, schema=destination.schema, name=name
        ),
        name,
    )


def _location(
    *, runtime: PlannerRuntime, database: str | None, schema: str | None, name: str
) -> CompiledRelationLocation:
    return CompiledRelationLocation(
        database=database,
        schema=schema,
        name=name,
        qualified_name=runtime.adapter.render_qualified_name(
            database=database, schema=schema, name=name
        ),
    )


def _with_execution(
    *, runtime: PlannerRuntime, model: CompiledModelView, entry: ModelMigrationPlanEntry
) -> ModelMigrationPlanEntry:
    """Describe how the executor will stage and promote this migration."""

    stage_is_transient: bool | None = (
        model.config.table_type.value == TableType.TRANSIENT
        if runtime.adapter.adapter_name == BuiltinAdapter.SNOWFLAKE
        else None
    )
    stage: MigrationStagePlan = runtime.adapter.render_migration_stage(
        origin=entry.origin.qualified_name or entry.origin.name,
        stage=entry.destination.qualified_name or entry.destination.name,
        origin_is_transient=entry.origin_is_transient,
        stage_is_transient=stage_is_transient,
    )
    return replace(
        entry,
        stage_is_transient=stage_is_transient,
        transfer=stage.transfer,
        transfer_fallback=MigrationTransfer.COPY if stage.fallback_statements else None,
        promotion=_promotion(runtime=runtime, decision=entry.decision),
    )


def _promotion(*, runtime: PlannerRuntime, decision: MigrationDecision) -> MigrationPromotion:
    if runtime.adapter.supports_transactional_ddl():
        return MigrationPromotion.TRANSACTIONAL_RENAME
    if decision != MigrationDecision.MIGRATE and (
        runtime.adapter.adapter_name == BuiltinAdapter.SNOWFLAKE
    ):
        return MigrationPromotion.SWAP
    return MigrationPromotion.RENAME


def redirected_cursor_snapshots(
    *,
    runtime: PlannerRuntime,
    scope: PlannerScope,
    existing_relations: dict[str, RelationInfo],
    target_relations: dict[str, str],
    overrides: PlannerOverrides,
    deferral: DeferralInputs,
    origin_cursor_columns: dict[str, str] | None = None,
) -> dict[str, ModelCursorSnapshot]:
    """Re-read target cursors from where history lives before this run's migrations."""

    return gather_redirected_cursor_snapshots(
        project=runtime.project,
        adapter=runtime.adapter,
        connection=runtime.connection,
        existing_relations=existing_relations,
        target_relations=target_relations,
        cursor_scope=CursorSnapshotScope(
            model_keys=scope.selected_keys,
            runtime_producer_keys=scope.selected_keys,
            invocation_time=runtime.invocation_time,
            start_cursor_config=(
                runtime.project_config.cursors.start if runtime.project_config is not None else None
            ),
            cursor_overrides=overrides.cursor_overrides,
        ),
        full_refresh_model_names=effectively_full_refreshed_model_names(
            project=runtime.project, cli_full_refresh=overrides.full_refresh
        ),
        deferred_locations=deferral.deferred_locations,
        on_progress=runtime.on_progress,
        origin_cursor_columns=origin_cursor_columns,
    )
