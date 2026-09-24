"""Fingerprint-based discovery of renamed or relocated models."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from sqlbuild.adapter.contract.constants import QUALIFIED_NAME_SEPARATOR
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
from sqlbuild.compiler.migrations.types import MigrationDiscovery
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
_CONFIG_KEY: str = "config"
_MATERIALIZED_KEY: str = "materialized"


def discover_model_migrations(
    *,
    runtime: PlannerRuntime,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    manual_requests: tuple[ModelMigrationRequest, ...],
    state: MigrationStateInspection,
    project_schemas: set[str],
) -> ModelMigrationDiscovery:
    """Add unique one-to-one fingerprint matches to the explicit migration requests."""

    models: tuple[CompiledModel, ...] = _topological_models(runtime=runtime)
    new_names: frozenset[str] = _new_model_names(models=models, scope=scope, snapshot=snapshot)
    manual_renames: dict[str, str] = {
        request.model.name: request.raw_origin
        for request in manual_requests
        if request.raw_origin is not None and QUALIFIED_NAME_SEPARATOR not in request.raw_origin
    }
    discoverable: frozenset[str] = new_names - frozenset(manual_renames)
    if not discoverable and not manual_requests:
        return ModelMigrationDiscovery()
    metadata_jsons: dict[str, str] = _metadata_jsons(runtime=runtime, models=models)
    dialect: str | None = runtime.adapter.sql_analysis_dialect()
    if not discoverable:
        return ModelMigrationDiscovery(
            requests=manual_requests,
            destination_fingerprints=_destination_fingerprints(
                requests=manual_requests,
                renames=manual_renames,
                metadata_jsons=metadata_jsons,
                dialect=dialect,
            ),
        )
    state.inspect_schemas(schemas=project_schemas)
    candidates: tuple[Fingerprint, ...] = _origin_candidates(
        runtime=runtime, state=state, models=models
    )
    renames: dict[str, str]
    matches: dict[str, Fingerprint]
    ambiguous: dict[str, tuple[str, ...]]
    renames, matches, ambiguous = _match(
        models=models,
        new_names=new_names,
        manual_renames=manual_renames,
        candidates=candidates,
        metadata_jsons=metadata_jsons,
        dialect=dialect,
    )
    automatic: tuple[ModelMigrationRequest, ...] = tuple(
        ModelMigrationRequest(
            model=model,
            discovery=MigrationDiscovery.AUTOMATIC,
            origin_location=_fingerprint_location(runtime=runtime, fingerprint=matches[model.name]),
            origin_model=matches[model.name].node_name,
        )
        for model in models
        if model.name in matches
        and model.key in scope.selected_keys
        and _moves_history(model=model, origin=matches[model.name])
    )
    requests: tuple[ModelMigrationRequest, ...] = (*manual_requests, *automatic)
    return ModelMigrationDiscovery(
        requests=requests,
        warnings=tuple(
            PlanWarning(
                model_name=model_name,
                severity=WarningSeverity.WARNING,
                message=(
                    f"'{model_name}' matches several earlier models ({', '.join(origins)}); "
                    "no automatic migration was inferred. Add migrate_from to choose one."
                ),
                code="M107",
            )
            for model_name, origins in sorted(ambiguous.items())
        ),
        destination_fingerprints=_destination_fingerprints(
            requests=requests, renames=renames, metadata_jsons=metadata_jsons, dialect=dialect
        ),
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
    manual_renames: dict[str, str],
    candidates: tuple[Fingerprint, ...],
    metadata_jsons: dict[str, str],
    dialect: str | None,
) -> tuple[dict[str, str], dict[str, Fingerprint], dict[str, tuple[str, ...]]]:
    by_fingerprint: dict[str, list[Fingerprint]] = defaultdict(list)
    candidate: Fingerprint
    for candidate in candidates:
        by_fingerprint[stored_migration_fingerprint(candidate) or ""].append(candidate)
    claimed_by_manual: frozenset[str] = frozenset(manual_renames.values())
    blocked: set[str] = set()
    ambiguous: dict[str, tuple[str, ...]] = {}
    for _ in range(len(candidates) + 1):
        renames: dict[str, str] = dict(manual_renames)
        matches: dict[str, Fingerprint] = {}
        claims: dict[str, list[str]] = defaultdict(list)
        model: CompiledModel
        for model in models:
            if model.name not in new_names or model.name in manual_renames:
                continue
            fingerprint: str | None = build_migration_fingerprint(
                query_sql=model.query_sql,
                metadata_json=metadata_jsons[model.name],
                ref_identities=renames,
                dialect=dialect,
            )
            options: list[Fingerprint] = [
                option
                for option in by_fingerprint.get(fingerprint or "", [])
                if option.node_name not in blocked and option.node_name not in claimed_by_manual
            ]
            if len(options) > 1:
                ambiguous[model.name] = tuple(sorted(option.node_name for option in options))
                continue
            if len(options) == 1:
                renames[model.name] = options[0].node_name
                matches[model.name] = options[0]
                claims[options[0].node_name].append(model.name)
        contested: dict[str, list[str]] = {
            origin: names for origin, names in claims.items() if len(names) > 1
        }
        if not contested:
            return renames, matches, ambiguous
        origin: str
        names: list[str]
        for origin, names in contested.items():
            blocked.add(origin)
            name: str
            for name in names:
                ambiguous[name] = (*ambiguous.get(name, ()), origin)
    return dict(manual_renames), {}, ambiguous


def _destination_fingerprints(
    *,
    requests: tuple[ModelMigrationRequest, ...],
    renames: dict[str, str],
    metadata_jsons: dict[str, str],
    dialect: str | None,
) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    request: ModelMigrationRequest
    for request in requests:
        metadata_json: str | None = metadata_jsons.get(request.model.name)
        if metadata_json is None:
            continue
        fingerprint: str | None = build_migration_fingerprint(
            query_sql=request.model.query_sql,
            metadata_json=metadata_json,
            ref_identities=renames,
            dialect=dialect,
        )
        if fingerprint is not None:
            fingerprints[request.model.name] = fingerprint
    return fingerprints


def _moves_history(*, model: CompiledModel, origin: Fingerprint) -> bool:
    return (
        get_config_str(values=model.config.values, key=_MATERIALIZED_KEY)
        in _HISTORY_MATERIALIZATIONS
        and _stored_materialization(origin) in _HISTORY_MATERIALIZATIONS
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
