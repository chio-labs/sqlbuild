"""Fingerprint-based discovery of renamed models within the project's schemas."""

from __future__ import annotations

import json
from typing import Any

from sqlbuild._native import (
    build_function_local_hashes,
    build_model_version_identity_metadata_json,
    get_config_str,
    match_migration_fingerprints,
    migration_destination_fingerprints,
    stored_migration_fingerprint,
)
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledModelView, CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.migrations.main._newest_event import newest_migration_event_mentioning
from sqlbuild.compiler.migrations.main.relation_for_location import (
    migration_relation_for_location,
)
from sqlbuild.compiler.migrations.models import MigrationEvent, MigrationRelation
from sqlbuild.compiler.migrations.types import MigrationDecision, MigrationDiscovery
from sqlbuild.compiler.planner.classes.migration_fingerprint_cache import (
    MigrationFingerprintCache,
)
from sqlbuild.compiler.planner.classes.migration_state_inspection import (
    MigrationStateInspection,
)
from sqlbuild.compiler.planner.models import (
    ModelMigrationDeclaration,
    ModelMigrationDiscovery,
    ModelMigrationRequest,
    PlannerRuntime,
    PlannerScope,
    PlanWarning,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import MaterializationType, WarningSeverity
from sqlbuild.compiler.python_nodes.main._hook_identities import build_hook_identities

_HISTORY_MATERIALIZATIONS: frozenset[str] = frozenset(
    {MaterializationType.INCREMENTAL, MaterializationType.SNAPSHOT}
)
_IDENTITY_MATERIALIZATIONS: frozenset[str] = frozenset(
    {MaterializationType.TABLE, MaterializationType.VIEW}
)
_CONFIG_KEY: str = "config"
_MATERIALIZED_KEY: str = "materialized"


def discover_model_migrations(
    *,
    runtime: PlannerRuntime,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    manual_requests: tuple[ModelMigrationRequest, ...],
    declarations: tuple[ModelMigrationDeclaration, ...],
    state: MigrationStateInspection,
    project_schemas: set[str],
    fingerprints: MigrationFingerprintCache,
) -> ModelMigrationDiscovery:
    """Add unique one-to-one fingerprint matches to the explicit migration requests."""

    models: tuple[CompiledModelView, ...] = _topological_models(runtime=runtime)
    declared: frozenset[str] = frozenset(item.model_name for item in declarations)
    triggered: bool = bool(
        _new_model_names(models=models, scope=scope, snapshot=snapshot) - declared
    )
    if not triggered and not manual_requests:
        return ModelMigrationDiscovery()
    metadata_jsons: dict[str, str] = _metadata_jsons(runtime=runtime, models=models)
    dialect: str | None = runtime.adapter.sql_analysis_dialect()
    state.inspect_schemas(schemas=project_schemas)
    declared_renames: dict[str, str] = _declared_renames(declarations=declarations, state=state)
    event_renames: dict[str, str] = _event_renames(runtime=runtime, models=models, state=state)
    seed_variants: tuple[dict[str, str], ...] = (
        {**event_renames, **declared_renames},
        dict(declared_renames),
    )
    if not triggered:
        return ModelMigrationDiscovery(
            requests=manual_requests,
            destination_fingerprints=migration_destination_fingerprints(
                requests=manual_requests,
                variants=seed_variants,
                metadata_jsons=metadata_jsons,
                dialect=dialect,
                fingerprints=fingerprints,
            ),
        )
    unbuilt: frozenset[str] = frozenset(
        model.name
        for model in models
        if model.name not in declared and state.named_fingerprint(model_name=model.name) is None
    )
    resumed: dict[str, MigrationEvent] = _resumed_events(
        runtime=runtime, models=models, unbuilt=unbuilt, state=state
    )
    candidates: tuple[Fingerprint, ...] = _origin_candidates(
        runtime=runtime,
        state=state,
        models=models,
        excluded=_claimed_origins(declarations=declarations, resumed=resumed),
    )
    variants: tuple[dict[str, str], ...]
    matches: dict[str, Fingerprint]
    ambiguous: dict[str, str]
    variants, matches, ambiguous = match_migration_fingerprints(
        models=models,
        new_names=unbuilt - frozenset(resumed),
        seed_variants=seed_variants,
        candidates=candidates,
        metadata_jsons=metadata_jsons,
        dialect=dialect,
        fingerprints=fingerprints,
    )
    requests: tuple[ModelMigrationRequest, ...] = (
        *manual_requests,
        *_automatic_requests(
            runtime=runtime, scope=scope, models=models, matches=matches, resumed=resumed
        ),
    )
    return ModelMigrationDiscovery(
        requests=requests,
        warnings=_ambiguity_warnings(models=models, scope=scope, ambiguous=ambiguous),
        destination_fingerprints=migration_destination_fingerprints(
            requests=requests,
            variants=variants,
            metadata_jsons=metadata_jsons,
            dialect=dialect,
            fingerprints=fingerprints,
        ),
    )


def _declared_renames(
    *, declarations: tuple[ModelMigrationDeclaration, ...], state: MigrationStateInspection
) -> dict[str, str]:
    """Map each explicitly migrated model to the model name its origin was built as."""

    renames: dict[str, str] = {}
    declaration: ModelMigrationDeclaration
    for declaration in declarations:
        origin_fingerprint: Fingerprint | None = state.model_fingerprint(
            location=declaration.origin_location, model_name=declaration.origin_model
        )
        origin_model: str | None = declaration.origin_model or (
            origin_fingerprint.node_name if origin_fingerprint is not None else None
        )
        if origin_model is not None:
            renames[declaration.model_name] = origin_model
    return renames


def _event_renames(
    *,
    runtime: PlannerRuntime,
    models: tuple[CompiledModelView, ...],
    state: MigrationStateInspection,
) -> dict[str, str]:
    """Map project models to the removed model their latest recorded move came from."""

    project_names: frozenset[str] = frozenset(model.name for model in models)
    target_name: str | None = runtime.project.effective_target_name
    latest: dict[str, MigrationEvent] = {}
    event: MigrationEvent
    for event in sorted(state.events, key=lambda item: (item.created_at, item.event_id)):
        if event.target_name in (None, target_name):
            latest[event.destination_model] = event
    return {
        name: event.origin_model
        for name, event in latest.items()
        if name in project_names
        and event.origin_model is not None
        and event.origin_model not in project_names
    }


def _resumed_events(
    *,
    runtime: PlannerRuntime,
    models: tuple[CompiledModelView, ...],
    unbuilt: frozenset[str],
    state: MigrationStateInspection,
) -> dict[str, MigrationEvent]:
    """Return recorded moves or renames into models that have not been built since."""

    target_name: str | None = runtime.project.effective_target_name
    resumed: dict[str, MigrationEvent] = {}
    model: CompiledModelView
    for model in models:
        if model.name not in unbuilt or not (_stores_history(model) or _hands_over_identity(model)):
            continue
        destination: MigrationRelation = migration_relation_for_location(model.destination)
        newest: MigrationEvent | None = newest_migration_event_mentioning(
            events=state.events, relation=destination
        )
        if (
            newest is not None
            and newest.destination.matches(destination)
            and newest.target_name in (None, target_name)
            and (newest.decision == MigrationDecision.RENAMED) is _hands_over_identity(model)
        ):
            resumed[model.name] = newest
    return resumed


def _claimed_origins(
    *,
    declarations: tuple[ModelMigrationDeclaration, ...],
    resumed: dict[str, MigrationEvent],
) -> frozenset[tuple[str, str]]:
    """Return relation keys already claimed by explicit or recorded migrations."""

    declared: set[tuple[str, str]] = {
        _relation_key(schema=item.origin_location.schema, name=item.origin_location.name)
        for item in declarations
    }
    recorded: set[tuple[str, str]] = {
        _relation_key(schema=event.origin.schema, name=event.origin.name)
        for event in resumed.values()
    }
    return frozenset(declared | recorded)


def _relation_key(*, schema: str | None, name: str) -> tuple[str, str]:
    return ((schema or "").lower(), name.lower())


def _automatic_requests(
    *,
    runtime: PlannerRuntime,
    scope: PlannerScope,
    models: tuple[CompiledModelView, ...],
    matches: dict[str, Fingerprint],
    resumed: dict[str, MigrationEvent],
) -> tuple[ModelMigrationRequest, ...]:
    """Return automatic requests for selected destinations only."""

    requests: list[ModelMigrationRequest] = []
    model: CompiledModelView
    for model in models:
        if model.key not in scope.selected_keys:
            continue
        event: MigrationEvent | None = resumed.get(model.name)
        match: Fingerprint | None = matches.get(model.name)
        if event is not None:
            requests.append(
                ModelMigrationRequest(
                    model=model,
                    discovery=MigrationDiscovery.AUTOMATIC,
                    origin_location=_event_origin_location(runtime=runtime, event=event),
                    origin_model=event.origin_model,
                    identity_only=_hands_over_identity(model),
                )
            )
        elif match is not None and (
            _moves_history(model=model, origin=match)
            or _renames_identity(model=model, origin=match)
        ):
            requests.append(
                ModelMigrationRequest(
                    model=model,
                    discovery=MigrationDiscovery.AUTOMATIC,
                    origin_location=_fingerprint_location(runtime=runtime, fingerprint=match),
                    origin_model=match.node_name,
                    identity_only=_hands_over_identity(model),
                )
            )
    return tuple(requests)


def _event_origin_location(
    *, runtime: PlannerRuntime, event: MigrationEvent
) -> CompiledRelationLocation:
    return CompiledRelationLocation(
        database=event.origin.database,
        schema=event.origin.schema,
        name=event.origin.name,
        qualified_name=runtime.adapter.render_qualified_name(
            database=event.origin.database, schema=event.origin.schema, name=event.origin.name
        ),
    )


def _ambiguity_warnings(
    *, models: tuple[CompiledModelView, ...], scope: PlannerScope, ambiguous: dict[str, str]
) -> tuple[PlanWarning, ...]:
    selected: frozenset[str] = frozenset(
        model.name for model in models if model.key in scope.selected_keys
    )
    return tuple(
        PlanWarning(
            model_name=model_name,
            severity=WarningSeverity.WARNING,
            message=(
                f"'{model_name}' matches {detail}; no automatic migration was inferred. "
                "Add migrate_from to choose one."
            ),
            code="M107",
        )
        for model_name, detail in sorted(ambiguous.items())
        if model_name in selected
    )


def _topological_models(*, runtime: PlannerRuntime) -> tuple[CompiledModelView, ...]:
    by_name: dict[str, CompiledModelView] = {model.name: model for model in runtime.project.models}
    ordered: list[CompiledModelView] = []
    visited: set[str] = set()
    pending: list[tuple[str, bool]] = [(name, False) for name in sorted(by_name, reverse=True)]
    while pending:
        name: str
        expanded: bool
        name, expanded = pending.pop()
        if expanded:
            ordered.append(by_name[name])
            continue
        if name in visited:
            continue
        visited.add(name)
        pending.append((name, True))
        pending.extend(
            (dep.name, False)
            for dep in sorted(by_name[name].deps, key=lambda key: key.name, reverse=True)
            if dep.resource_type == CompiledResourceType.MODEL
            and dep.name in by_name
            and dep.name not in visited
        )
    return tuple(ordered)


def _new_model_names(
    *, models: tuple[CompiledModelView, ...], scope: PlannerScope, snapshot: WarehouseSnapshot
) -> frozenset[str]:
    relevant: set[CompiledObjectKey] = set(scope.selected_keys)
    frontier: list[CompiledObjectKey] = list(scope.selected_keys)
    while frontier:
        key: CompiledObjectKey = frontier.pop()
        upstream: CompiledObjectKey
        for upstream in scope.upstream_deps.get(key, ()):
            if upstream not in relevant:
                relevant.add(upstream)
                frontier.append(upstream)
    return frozenset(
        model.name
        for model in models
        if model.key in relevant and model.name not in snapshot.fingerprints.models
    )


def _metadata_jsons(
    *, runtime: PlannerRuntime, models: tuple[CompiledModelView, ...]
) -> dict[str, str]:
    function_hashes: dict[str, str] = build_function_local_hashes(
        functions=runtime.project.functions, dialect=runtime.project.sql_analysis_dialect
    )
    hook_hashes: dict[str, str] = {
        name: identity.version_hash
        for name, identity in build_hook_identities(runtime.project.hook_functions).items()
    }
    return {
        model.name: build_model_version_identity_metadata_json(
            model=model, function_local_hashes=function_hashes, hook_version_hashes=hook_hashes
        )
        for model in models
    }


def _origin_candidates(
    *,
    runtime: PlannerRuntime,
    state: MigrationStateInspection,
    models: tuple[CompiledModelView, ...],
    excluded: frozenset[tuple[str, str]],
) -> tuple[Fingerprint, ...]:
    project_model_names: frozenset[str] = frozenset(model.name for model in models)
    orphans: tuple[Fingerprint, ...] = tuple(
        fingerprint
        for fingerprint in state.orphan_fingerprints(project_model_names=project_model_names)
        if stored_migration_fingerprint(fingerprint) is not None
        and fingerprint.target_name is not None
    )
    locations: tuple[CompiledRelationLocation, ...] = tuple(
        _fingerprint_location(runtime=runtime, fingerprint=fingerprint) for fingerprint in orphans
    )
    state.inspect_relations(locations=locations)
    return tuple(
        fingerprint
        for fingerprint, location in zip(orphans, locations, strict=True)
        if state.relation(location) is not None
        and _relation_key(schema=location.schema, name=location.name) not in excluded
        and not _superseded(events=state.events, location=location)
    )


def _superseded(*, events: tuple[MigrationEvent, ...], location: CompiledRelationLocation) -> bool:
    relation: MigrationRelation = migration_relation_for_location(location)
    newest: MigrationEvent | None = newest_migration_event_mentioning(
        events=events, relation=relation
    )
    return newest is not None and newest.origin.matches(relation)


def _moves_history(*, model: CompiledModelView, origin: Fingerprint) -> bool:
    return _stores_history(model) and _stored_materialization(origin) in _HISTORY_MATERIALIZATIONS


def _renames_identity(*, model: CompiledModelView, origin: Fingerprint) -> bool:
    return (
        _hands_over_identity(model)
        and _stored_materialization(origin) in _IDENTITY_MATERIALIZATIONS
    )


def _hands_over_identity(model: CompiledModelView) -> bool:
    return (
        get_config_str(values=model.config.values, key=_MATERIALIZED_KEY)
        in _IDENTITY_MATERIALIZATIONS
    )


def _stores_history(model: CompiledModelView) -> bool:
    return (
        get_config_str(values=model.config.values, key=_MATERIALIZED_KEY)
        in _HISTORY_MATERIALIZATIONS
    )


def _stored_materialization(fingerprint: Fingerprint) -> str | None:
    payload: Any = _metadata_payload(fingerprint)
    config: Any = payload.get(_CONFIG_KEY) if payload else None
    value: Any = config.get(_MATERIALIZED_KEY) if isinstance(config, dict) else None
    return value if isinstance(value, str) else None


def _metadata_payload(fingerprint: Fingerprint) -> dict[str, Any] | None:
    try:
        payload: Any = json.loads(fingerprint.metadata_json)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _fingerprint_location(
    *, runtime: PlannerRuntime, fingerprint: Fingerprint
) -> CompiledRelationLocation:
    name: str = fingerprint.target_name or fingerprint.node_name
    return CompiledRelationLocation(
        database=fingerprint.target_database,
        schema=fingerprint.target_schema,
        name=name,
        qualified_name=runtime.adapter.render_qualified_name(
            database=fingerprint.target_database, schema=fingerprint.target_schema, name=name
        ),
    )
