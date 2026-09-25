"""Per-run decisions for direct-mode model migrations."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime

from sqlbuild.adapter.contract.models import ColumnInfo, MigrationStagePlan, RelationInfo
from sqlbuild.adapter.contract.types import BuiltinAdapter
from sqlbuild.compiler.compile.constants import MIGRATE_FORCE_CONFIG_KEY, MIGRATE_FROM_CONFIG_KEY
from sqlbuild.compiler.compile.models import CompiledModel, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.migrations.main._newest_event import newest_migration_event_mentioning
from sqlbuild.compiler.migrations.main.relation_for_location import migration_relation_for_location
from sqlbuild.compiler.migrations.models import MigrationEvent
from sqlbuild.compiler.migrations.types import (
    MigrationCompatibility,
    MigrationDecision,
    MigrationDiscovery,
    MigrationPromotion,
)
from sqlbuild.compiler.planner._helpers.migrations.compatibility import (
    MigrationCompatibilityResult,
    check_migration_compatibility,
)
from sqlbuild.compiler.planner._helpers.migrations.discovery import (
    discover_model_migrations,
    stored_migration_fingerprint,
)
from sqlbuild.compiler.planner._helpers.planning.full_refresh import (
    effectively_full_refreshed_model_names,
)
from sqlbuild.compiler.planner._helpers.warehouse.snapshot import (
    gather_redirected_cursor_snapshots,
)
from sqlbuild.compiler.planner.classes.migration_state_inspection import (
    MigrationStateInspection,
)
from sqlbuild.compiler.planner.constants import (
    MIGRATION_MODEL_NAME_METADATA_KEY,
    QUALIFIED_RELATION_MAX_PARTS,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import (
    CursorSnapshotScope,
    DeferralInputs,
    ModelCursorSnapshot,
    ModelMigrationDeclaration,
    ModelMigrationDiscovery,
    ModelMigrationPlanEntry,
    ModelMigrationPlanning,
    ModelMigrationRequest,
    PlannerOverrides,
    PlannerRuntime,
    PlannerScope,
    PlanWarning,
    WarehouseFingerprints,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import MaterializationType, WarningSeverity
from sqlbuild.spec.contracts.main.get_config_str import get_config_str
from sqlbuild.spec.contracts.models import SnapshotsConfig
from sqlbuild.spec.contracts.types import TableType


def manual_migration_requests(*, scope: PlannerScope) -> tuple[ModelMigrationRequest, ...]:
    """Collect selected models that declare migrate_from."""

    requests: list[ModelMigrationRequest] = []
    key: object
    for key in scope.execution_order:
        if key not in scope.selected_keys or getattr(key, "resource_type", None) != (
            CompiledResourceType.MODEL
        ):
            continue
        model: CompiledModel | None = scope.models_by_name.get(getattr(key, "name", ""))
        request: ModelMigrationRequest | None = None if model is None else _declared_request(model)
        if request is not None:
            requests.append(request)
    return tuple(requests)


def _declared_request(model: CompiledModel) -> ModelMigrationRequest | None:
    raw_origin: object | None = model.config.values.get(MIGRATE_FROM_CONFIG_KEY)
    if not isinstance(raw_origin, str):
        return None
    return ModelMigrationRequest(
        model=model,
        discovery=MigrationDiscovery.MANUAL,
        raw_origin=raw_origin.strip(),
        force=model.config.values.get(MIGRATE_FORCE_CONFIG_KEY) is True,
    )


def _project_declarations(
    *, runtime: PlannerRuntime, state: MigrationStateInspection
) -> tuple[ModelMigrationDeclaration, ...]:
    """Resolve every project model's migrate_from, selected or not."""

    declarations: list[ModelMigrationDeclaration] = []
    model: CompiledModel
    for model in runtime.project.models:
        request: ModelMigrationRequest | None = _declared_request(model)
        if request is None:
            continue
        origin: CompiledRelationLocation
        origin_model: str | None
        origin, origin_model = _resolve_origin(request=request, runtime=runtime, state=state)
        declarations.append(
            ModelMigrationDeclaration(
                model_name=model.name, origin_location=origin, origin_model=origin_model
            )
        )
    return tuple(declarations)


def plan_model_migrations(
    *,
    runtime: PlannerRuntime,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    overrides: PlannerOverrides,
    deferral: DeferralInputs,
) -> ModelMigrationPlanning:
    """Decide every declared or discovered migration and project the post-migration snapshot."""

    manual: tuple[ModelMigrationRequest, ...] = manual_migration_requests(scope=scope)
    schemas: set[str] = project_schemas(runtime=runtime)
    state: MigrationStateInspection = MigrationStateInspection(
        adapter=runtime.adapter,
        connection=runtime.connection,
        database=planning_database(runtime=runtime),
    )
    declares_migrations: bool = any(
        _declared_request(model) is not None for model in runtime.project.models
    )
    if declares_migrations:
        state.inspect_schemas(schemas=schemas)
    discovery: ModelMigrationDiscovery = discover_model_migrations(
        runtime=runtime,
        scope=scope,
        snapshot=snapshot,
        manual_requests=manual,
        declarations=_project_declarations(runtime=runtime, state=state),
        state=state,
        project_schemas=schemas,
    )
    if not discovery.requests:
        return ModelMigrationPlanning(snapshot=snapshot, warnings=discovery.warnings)
    resolved: list[tuple[ModelMigrationRequest, CompiledRelationLocation, str | None]] = [
        (request, *_resolve_origin(request=request, runtime=runtime, state=state))
        for request in discovery.requests
    ]
    origin: CompiledRelationLocation
    for _, origin, _ in resolved:
        _require_same_database(state=state, location=origin)
    state.inspect_schemas(
        schemas={location.schema for _, location, _ in resolved if location.schema is not None}
    )
    state.inspect_relations(locations=tuple(location for _, location, _ in resolved))
    snapshots_config: SnapshotsConfig = (
        runtime.project_config.snapshots
        if runtime.project_config is not None
        else SnapshotsConfig()
    )
    entries: list[ModelMigrationPlanEntry] = []
    handovers: dict[str, Fingerprint | None] = {}
    request: ModelMigrationRequest
    origin: CompiledRelationLocation
    origin_model: str | None
    for request, origin, origin_model in resolved:
        entry: ModelMigrationPlanEntry
        handover: Fingerprint | None
        applies: bool
        entry, handover, applies = _decide(
            runtime=runtime,
            request=request,
            origin=origin,
            origin_model=origin_model,
            snapshot=snapshot,
            state=state,
            snapshots_config=snapshots_config,
        )
        entries.append(entry)
        if applies:
            handovers[request.model.name] = _equivalent_definition(
                model=request.model,
                handover=handover,
                destination_fingerprints=discovery.destination_fingerprints.get(
                    request.model.name, ()
                ),
            )
    renamed: frozenset[str] = _renamed_models(
        runtime=runtime, entries=tuple(entries), handovers=handovers
    )
    return ModelMigrationPlanning(
        snapshot=replace(
            _overlay_snapshot(
                runtime=runtime,
                scope=scope,
                snapshot=snapshot,
                entries=tuple(entries),
                handovers=_effective_handovers(
                    entries=tuple(entries), handovers=handovers, renamed=renamed
                ),
                state=state,
                overrides=overrides,
                deferral=deferral,
            ),
            renamed_models=renamed,
        ),
        entries=tuple(entries),
        warnings=(
            *discovery.warnings,
            *(warning for entry in entries if (warning := _entry_warning(entry)) is not None),
        ),
    )


def _renamed_models(
    *,
    runtime: PlannerRuntime,
    entries: tuple[ModelMigrationPlanEntry, ...],
    handovers: dict[str, Fingerprint | None],
) -> frozenset[str]:
    """Return renamed tables and views whose handed-over definition matches their own."""

    query_sql: dict[str, str] = {model.name: model.query_sql for model in runtime.project.models}
    return frozenset(
        entry.model_name
        for entry in entries
        if entry.decision == MigrationDecision.RENAMED
        and (handover := handovers.get(entry.model_name)) is not None
        and handover.definition == query_sql.get(entry.model_name)
    )


def _effective_handovers(
    *,
    entries: tuple[ModelMigrationPlanEntry, ...],
    handovers: dict[str, Fingerprint | None],
    renamed: frozenset[str],
) -> dict[str, Fingerprint | None]:
    """Drop the handover of any rename whose definition no longer matches."""

    unmatched: frozenset[str] = frozenset(
        entry.model_name
        for entry in entries
        if entry.decision == MigrationDecision.RENAMED and entry.model_name not in renamed
    )
    return {name: None if name in unmatched else handover for name, handover in handovers.items()}


def _equivalent_definition(
    *, model: CompiledModel, handover: Fingerprint | None, destination_fingerprints: tuple[str, ...]
) -> Fingerprint | None:
    if handover is None or stored_migration_fingerprint(handover) not in destination_fingerprints:
        return handover
    return replace(
        handover,
        definition=model.query_sql,
        definition_hash=compute_query_hash(model.query_sql),
    )


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


def _relation_key(location: CompiledRelationLocation) -> tuple[str, str]:
    return ((location.schema or "").lower(), location.name.lower())


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
    project_model: CompiledModel | None = next(
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


def _decide(
    *,
    runtime: PlannerRuntime,
    request: ModelMigrationRequest,
    origin: CompiledRelationLocation,
    origin_model: str | None,
    snapshot: WarehouseSnapshot,
    state: MigrationStateInspection,
    snapshots_config: SnapshotsConfig,
) -> tuple[ModelMigrationPlanEntry, Fingerprint | None, bool]:
    model: CompiledModel = request.model
    destination: CompiledRelationLocation = model.destination
    if _relation_key(origin) == _relation_key(destination):
        raise PlannerInputError(
            f"model '{model.name}': migrate_from names the model's own relation"
        )
    newest: MigrationEvent | None = newest_migration_event_mentioning(
        events=state.events, relation=migration_relation_for_location(destination)
    )
    origin_relation: RelationInfo | None = state.relation(origin)
    origin_fingerprint: Fingerprint | None = state.model_fingerprint(
        location=origin, model_name=origin_model
    )
    base: ModelMigrationPlanEntry = ModelMigrationPlanEntry(
        model_name=model.name,
        discovery=request.discovery,
        decision=MigrationDecision.MIGRATE,
        compatibility=MigrationCompatibility.NOT_CHECKED,
        origin_model=origin_model,
        origin=origin,
        destination=destination,
        target_name=runtime.project.effective_target_name,
        origin_version_hash=(
            origin_fingerprint.version_hash if origin_fingerprint is not None else ""
        ),
        origin_is_transient=bool(origin_relation is not None and origin_relation.is_transient),
    )
    if request.identity_only:
        return _decide_rename(
            model=model,
            base=base,
            newest=newest,
            origin=origin,
            origin_fingerprint=origin_fingerprint,
        )
    if (
        newest is not None
        and newest.destination.matches(migration_relation_for_location(destination))
        and newest.origin.matches(migration_relation_for_location(origin))
    ):
        return (
            replace(
                base,
                decision=MigrationDecision.DONE,
                completed_at=newest.created_at,
                origin_version_hash=newest.origin_version_hash,
                target_name=newest.target_name,
            ),
            _done_handover(
                model=model,
                event=newest,
                snapshot=snapshot,
                origin_fingerprint=origin_fingerprint,
            ),
            _done_handover_applies(model=model, event=newest, snapshot=snapshot),
        )
    if origin_relation is None:
        return replace(base, decision=MigrationDecision.ORIGIN_MISSING), None, False
    compatibility: MigrationCompatibilityResult = check_migration_compatibility(
        model=model,
        origin_relation=origin_relation,
        origin_columns=state.relation_columns(origin),
        sql_analysis_enabled=runtime.project.settings.sql_analysis,
        column_dialect=snapshot.column_dialect,
        snapshots_config=snapshots_config,
    )
    decision: MigrationDecision
    if model.name not in snapshot.existing_relations:
        decision = MigrationDecision.MIGRATE
    elif newest is not None and newest.origin.matches(migration_relation_for_location(destination)):
        decision = MigrationDecision.SUPERSEDED_REPLACE
    elif newest is None and model.name not in snapshot.fingerprints.models:
        decision = MigrationDecision.REDO
    elif request.force:
        decision = MigrationDecision.FORCED_REPLACE
    else:
        decision = MigrationDecision.CONFLICT
    entry: ModelMigrationPlanEntry = replace(
        base,
        decision=decision,
        compatibility=compatibility.status,
        compatibility_findings=compatibility.findings,
    )
    if not decision.moves_data or entry.blocks_build:
        return entry, None, False
    return (
        _with_execution(runtime=runtime, model=model, entry=entry),
        _handover_fingerprint(
            model=model,
            fingerprint=origin_fingerprint,
            version_hash=entry.origin_version_hash,
        ),
        True,
    )


def _decide_rename(
    *,
    model: CompiledModel,
    base: ModelMigrationPlanEntry,
    newest: MigrationEvent | None,
    origin: CompiledRelationLocation,
    origin_fingerprint: Fingerprint | None,
) -> tuple[ModelMigrationPlanEntry, Fingerprint | None, bool]:
    """Hand a renamed table or view's identity to its unbuilt successor; no data moves."""

    recorded: bool = (
        newest is not None
        and newest.decision == MigrationDecision.RENAMED
        and newest.destination.matches(migration_relation_for_location(model.destination))
        and newest.origin.matches(migration_relation_for_location(origin))
    )
    return (
        replace(
            base,
            decision=MigrationDecision.RENAMED,
            completed_at=newest.created_at if recorded and newest is not None else None,
        ),
        _handover_fingerprint(model=model, fingerprint=origin_fingerprint, version_hash=""),
        True,
    )


def _with_execution(
    *, runtime: PlannerRuntime, model: CompiledModel, entry: ModelMigrationPlanEntry
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


def _done_handover_applies(
    *, model: CompiledModel, event: MigrationEvent, snapshot: WarehouseSnapshot
) -> bool:
    own: Fingerprint | None = snapshot.fingerprints.models.get(model.name)
    return own is None or _utc(own.ts) < _utc(event.created_at)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _done_handover(
    *,
    model: CompiledModel,
    event: MigrationEvent,
    snapshot: WarehouseSnapshot,
    origin_fingerprint: Fingerprint | None,
) -> Fingerprint | None:
    if not _done_handover_applies(model=model, event=event, snapshot=snapshot):
        return snapshot.fingerprints.models.get(model.name)
    return _handover_fingerprint(
        model=model, fingerprint=origin_fingerprint, version_hash=event.origin_version_hash
    )


def _handover_fingerprint(
    *, model: CompiledModel, fingerprint: Fingerprint | None, version_hash: str
) -> Fingerprint | None:
    if fingerprint is None:
        return None
    metadata_json: str = fingerprint.metadata_json
    try:
        payload: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict) and MIGRATION_MODEL_NAME_METADATA_KEY in payload:
        payload[MIGRATION_MODEL_NAME_METADATA_KEY] = model.name
        metadata_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return replace(
        fingerprint,
        node_name=model.name,
        target_database=model.destination.database,
        target_schema=model.destination.schema,
        target_name=model.destination.name,
        version_hash=version_hash or fingerprint.version_hash,
        metadata_json=metadata_json,
    )


def _overlay_snapshot(
    *,
    runtime: PlannerRuntime,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    entries: tuple[ModelMigrationPlanEntry, ...],
    handovers: dict[str, Fingerprint | None],
    state: MigrationStateInspection,
    overrides: PlannerOverrides,
    deferral: DeferralInputs,
) -> WarehouseSnapshot:
    if not handovers:
        return snapshot
    relations: dict[str, RelationInfo] = dict(snapshot.existing_relations)
    columns: dict[str, tuple[ColumnInfo, ...]] = dict(snapshot.existing_columns)
    model_fingerprints: dict[str, Fingerprint] = dict(snapshot.fingerprints.models)
    redirected: dict[str, str] = {}
    entry: ModelMigrationPlanEntry
    for entry in entries:
        if entry.model_name not in handovers:
            continue
        handover: Fingerprint | None = handovers[entry.model_name]
        if handover is None:
            _ = model_fingerprints.pop(entry.model_name, None)
        else:
            model_fingerprints[entry.model_name] = handover
        if not entry.decision.moves_data:
            continue
        origin_relation: RelationInfo | None = state.relation(entry.origin)
        if origin_relation is None:
            continue
        relations[entry.model_name] = replace(
            origin_relation,
            database=entry.destination.database,
            schema=entry.destination.schema,
            name=entry.destination.name,
            is_transient=(
                origin_relation.is_transient
                if entry.stage_is_transient is None
                else entry.stage_is_transient
            ),
        )
        columns[entry.model_name] = state.relation_columns(entry.origin)
        if entry.origin.qualified_name is not None and _has_cursor(
            runtime=runtime, model_name=entry.model_name
        ):
            redirected[entry.model_name] = entry.origin.qualified_name
    cursor_snapshots: dict[str, ModelCursorSnapshot] = {
        **snapshot.cursor_snapshots,
        **gather_redirected_cursor_snapshots(
            project=runtime.project,
            adapter=runtime.adapter,
            connection=runtime.connection,
            existing_relations=relations,
            target_relations=redirected,
            cursor_scope=CursorSnapshotScope(
                model_keys=scope.selected_keys,
                runtime_producer_keys=scope.selected_keys,
                invocation_time=runtime.invocation_time,
                start_cursor_config=(
                    runtime.project_config.cursors.start
                    if runtime.project_config is not None
                    else None
                ),
                cursor_overrides=overrides.cursor_overrides,
            ),
            full_refresh_model_names=effectively_full_refreshed_model_names(
                project=runtime.project, cli_full_refresh=overrides.full_refresh
            ),
            deferred_locations=deferral.deferred_locations,
            on_progress=runtime.on_progress,
        ),
    }
    return replace(
        snapshot,
        existing_relations=relations,
        existing_columns=columns,
        fingerprints=WarehouseFingerprints(
            models=model_fingerprints,
            functions=snapshot.fingerprints.functions,
            seeds=snapshot.fingerprints.seeds,
            python_nodes=snapshot.fingerprints.python_nodes,
        ),
        cursor_snapshots=cursor_snapshots,
    )


def _has_cursor(*, runtime: PlannerRuntime, model_name: str) -> bool:
    model: CompiledModel | None = next(
        (model for model in runtime.project.models if model.name == model_name), None
    )
    return (
        model is not None
        and get_config_str(values=model.config.values, key="materialized")
        == MaterializationType.INCREMENTAL
        and get_config_str(values=model.config.values, key="cursor") is not None
    )


def _entry_warning(entry: ModelMigrationPlanEntry) -> PlanWarning | None:
    origin: str = entry.origin.qualified_name or entry.origin.name
    destination: str = entry.destination.qualified_name or entry.destination.name
    if entry.decision == MigrationDecision.DONE:
        if entry.discovery != MigrationDiscovery.MANUAL:
            return None
        completed: str = entry.completed_at.isoformat() if entry.completed_at else "unknown time"
        return PlanWarning(
            model_name=entry.model_name,
            severity=WarningSeverity.WARNING,
            message=(
                f"migration from {origin} completed at {completed} on target "
                f"'{entry.target_name}'; migrate_from can be removed from '{entry.model_name}'"
            ),
            code="M101",
        )
    if entry.decision == MigrationDecision.ORIGIN_MISSING:
        return PlanWarning(
            model_name=entry.model_name,
            severity=WarningSeverity.ERROR,
            message=(
                f"model '{entry.model_name}': migrate_from origin {origin} does not exist and "
                "no recorded migration into it was found; if the migration already happened "
                "elsewhere or is no longer needed, remove migrate_from from the model header"
            ),
            code="M102",
        )
    if entry.decision == MigrationDecision.CONFLICT:
        return PlanWarning(
            model_name=entry.model_name,
            severity=WarningSeverity.ERROR,
            message=(
                f"migration conflict: {destination} already exists with its own build history "
                f"and has no recorded migration from {origin}; set migrate_force true to "
                "replace it (the replaced table is kept under a _sqb_archive__ name until "
                "janitor expires it)"
            ),
            code="M103",
        )
    if entry.blocks_build:
        return PlanWarning(
            model_name=entry.model_name,
            severity=WarningSeverity.ERROR,
            message=(
                f"migration from {origin} is incompatible with '{entry.model_name}': "
                + "; ".join(entry.compatibility_findings)
            ),
            code="M104",
        )
    return None
