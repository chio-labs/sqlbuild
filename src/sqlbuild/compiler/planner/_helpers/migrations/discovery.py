"""Fingerprint-based discovery of renamed models within the project's schemas."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.migrations.main._newest_event import newest_migration_event_mentioning
from sqlbuild.compiler.migrations.main.relation_for_location import (
    migration_relation_for_location,
)
from sqlbuild.compiler.migrations.models import MigrationEvent, MigrationRelation
from sqlbuild.compiler.migrations.types import MigrationDecision, MigrationDiscovery
from sqlbuild.compiler.planner._helpers.migrations.fingerprint import build_migration_fingerprint
from sqlbuild.compiler.planner.classes.migration_state_inspection import (
    MigrationStateInspection,
)
from sqlbuild.compiler.planner.constants import MIGRATION_FINGERPRINT_METADATA_KEY
from sqlbuild.compiler.planner.main.identity.version_identity_function_hashes import (
    build_function_local_hashes,
)
from sqlbuild.compiler.planner.main.identity.version_identity_model_metadata import (
    build_model_version_identity_metadata_json,
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
from sqlbuild.compiler.python_nodes.main.hook_identities import build_hook_identities
from sqlbuild.spec.contracts.main.get_config_str import get_config_str

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
) -> ModelMigrationDiscovery:
    """Add unique one-to-one fingerprint matches to the explicit migration requests."""

    models: tuple[CompiledModel, ...] = _topological_models(runtime=runtime)
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
            destination_fingerprints=_destination_fingerprints(
                requests=manual_requests,
                variants=seed_variants,
                metadata_jsons=metadata_jsons,
                dialect=dialect,
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
    variants, matches, ambiguous = _match(
        models=models,
        new_names=unbuilt - frozenset(resumed),
        seed_variants=seed_variants,
        candidates=candidates,
        metadata_jsons=metadata_jsons,
        dialect=dialect,
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
        destination_fingerprints=_destination_fingerprints(
            requests=requests, variants=variants, metadata_jsons=metadata_jsons, dialect=dialect
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
    *, runtime: PlannerRuntime, models: tuple[CompiledModel, ...], state: MigrationStateInspection
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
    models: tuple[CompiledModel, ...],
    unbuilt: frozenset[str],
    state: MigrationStateInspection,
) -> dict[str, MigrationEvent]:
    """Return recorded moves or renames into models that have not been built since."""

    target_name: str | None = runtime.project.effective_target_name
    resumed: dict[str, MigrationEvent] = {}
    model: CompiledModel
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
    models: tuple[CompiledModel, ...],
    matches: dict[str, Fingerprint],
    resumed: dict[str, MigrationEvent],
) -> tuple[ModelMigrationRequest, ...]:
    """Return automatic requests for selected destinations only."""

    requests: list[ModelMigrationRequest] = []
    model: CompiledModel
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
    *, models: tuple[CompiledModel, ...], scope: PlannerScope, ambiguous: dict[str, str]
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


def _topological_models(*, runtime: PlannerRuntime) -> tuple[CompiledModel, ...]:
    by_name: dict[str, CompiledModel] = {model.name: model for model in runtime.project.models}
    ordered: list[CompiledModel] = []
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
    *, models: tuple[CompiledModel, ...], scope: PlannerScope, snapshot: WarehouseSnapshot
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
    *, runtime: PlannerRuntime, models: tuple[CompiledModel, ...]
) -> dict[str, str]:
    function_hashes: dict[str, str] = build_function_local_hashes(
        functions=runtime.project.functions
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
    models: tuple[CompiledModel, ...],
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


def _match(
    *,
    models: tuple[CompiledModel, ...],
    new_names: frozenset[str],
    seed_variants: tuple[dict[str, str], ...],
    candidates: tuple[Fingerprint, ...],
    metadata_jsons: dict[str, str],
    dialect: str | None,
) -> tuple[tuple[dict[str, str], ...], dict[str, Fingerprint], dict[str, str]]:
    """Match unbuilt models to candidates under every rename-map variant."""

    by_fingerprint: dict[str, list[Fingerprint]] = defaultdict(list)
    candidate: Fingerprint
    for candidate in candidates:
        by_fingerprint[stored_migration_fingerprint(candidate) or ""].append(candidate)
    blocked: set[str] = set()
    ambiguous: dict[str, str] = {}
    for _ in range(len(candidates) + 1):
        variants: tuple[dict[str, str], ...] = tuple(dict(seed) for seed in seed_variants)
        matches: dict[str, Fingerprint] = {}
        claims: dict[str, list[str]] = defaultdict(list)
        model: CompiledModel
        for model in models:
            if model.name not in new_names:
                continue
            options: list[Fingerprint] = _match_options(
                fingerprints=_variant_fingerprints(
                    model=model,
                    metadata_json=metadata_jsons[model.name],
                    variants=variants,
                    dialect=dialect,
                ),
                by_fingerprint=by_fingerprint,
                blocked=blocked,
            )
            if len(options) > 1:
                ambiguous[model.name] = (
                    "several earlier models "
                    f"({', '.join(sorted(option.node_name for option in options))})"
                )
                continue
            if len(options) == 1:
                variant: dict[str, str]
                for variant in variants:
                    variant[model.name] = options[0].node_name
                matches[model.name] = options[0]
                claims[options[0].node_name].append(model.name)
        contested: dict[str, list[str]] = {
            origin: names for origin, names in claims.items() if len(names) > 1
        }
        if not contested:
            return variants, matches, ambiguous
        blocked.update(contested)
        ambiguous.update(_contested_details(contested))
    return tuple(dict(seed) for seed in seed_variants), {}, ambiguous


def _variant_fingerprints(
    *,
    model: CompiledModel,
    metadata_json: str,
    variants: tuple[dict[str, str], ...],
    dialect: str | None,
) -> tuple[str, ...]:
    """Return the distinct migration fingerprints of one model under each rename map."""

    fingerprints: list[str | None] = [
        build_migration_fingerprint(
            query_sql=model.query_sql,
            metadata_json=metadata_json,
            ref_identities=variant,
            dialect=dialect,
        )
        for variant in variants
    ]
    return tuple(dict.fromkeys(item for item in fingerprints if item is not None))


def _match_options(
    *,
    fingerprints: tuple[str, ...],
    by_fingerprint: dict[str, list[Fingerprint]],
    blocked: set[str],
) -> list[Fingerprint]:
    options: dict[str, Fingerprint] = {}
    fingerprint: str
    for fingerprint in fingerprints:
        options.update(
            {
                option.node_name: option
                for option in by_fingerprint.get(fingerprint, [])
                if option.node_name not in blocked
            }
        )
    return list(options.values())


def _contested_details(contested: dict[str, list[str]]) -> dict[str, str]:
    """Describe each model that shares its only matching earlier model with others."""

    details: dict[str, str] = {}
    origin: str
    names: list[str]
    for origin, names in contested.items():
        name: str
        for name in names:
            others: list[str] = [f"'{other}'" for other in sorted(names) if other != name]
            details[name] = f"earlier model '{origin}', which also matches {', '.join(others)}"
    return details


def _destination_fingerprints(
    *,
    requests: tuple[ModelMigrationRequest, ...],
    variants: tuple[dict[str, str], ...],
    metadata_jsons: dict[str, str],
    dialect: str | None,
) -> dict[str, tuple[str, ...]]:
    fingerprints: dict[str, tuple[str, ...]] = {}
    request: ModelMigrationRequest
    for request in requests:
        metadata_json: str | None = metadata_jsons.get(request.model.name)
        if metadata_json is None:
            continue
        fingerprints[request.model.name] = _variant_fingerprints(
            model=request.model, metadata_json=metadata_json, variants=variants, dialect=dialect
        )
    return fingerprints


def _moves_history(*, model: CompiledModel, origin: Fingerprint) -> bool:
    return _stores_history(model) and _stored_materialization(origin) in _HISTORY_MATERIALIZATIONS


def _renames_identity(*, model: CompiledModel, origin: Fingerprint) -> bool:
    return (
        _hands_over_identity(model)
        and _stored_materialization(origin) in _IDENTITY_MATERIALIZATIONS
    )


def _hands_over_identity(model: CompiledModel) -> bool:
    return (
        get_config_str(values=model.config.values, key=_MATERIALIZED_KEY)
        in _IDENTITY_MATERIALIZATIONS
    )


def _stores_history(model: CompiledModel) -> bool:
    return (
        get_config_str(values=model.config.values, key=_MATERIALIZED_KEY)
        in _HISTORY_MATERIALIZATIONS
    )


def stored_migration_fingerprint(fingerprint: Fingerprint) -> str | None:
    """Return the migration fingerprint recorded in a model fingerprint row, if any."""

    payload: Any = _metadata_payload(fingerprint)
    value: Any = payload.get(MIGRATION_FINGERPRINT_METADATA_KEY) if payload else None
    return value if isinstance(value, str) else None


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
