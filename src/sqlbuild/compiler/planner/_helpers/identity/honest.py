"""Build direct model write hashes from actually available upstream identities."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import CompiledModel, CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner._helpers.identity.hashing import (
    compose_native_graph_identity,
    graph_key_for_compiled_resource,
)
from sqlbuild.compiler.planner.main.identity._graph_write_identity import (
    build_graph_write_identity_hashes,
)
from sqlbuild.compiler.planner.models import (
    ChangeDetectionResult,
    DirectModelVersionIdentities,
    GraphIdentityNode,
    GraphNodeKey,
    PlannerChangeResults,
    PlannerResolvedActions,
    PlannerScope,
    ResolvedModelAction,
    WarehouseSnapshot,
)
from sqlbuild.compiler.planner.types import ChangeKind, GraphResourceKind


def with_honest_model_write_hashes(
    *,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    changes: PlannerChangeResults,
    version_identities: DirectModelVersionIdentities,
    available_model_hashes: dict[str, str] | None = None,
) -> PlannerChangeResults:
    """Replace planned write hashes with hashes based on upstreams available this run."""

    base_hashes: dict[GraphNodeKey, str] = _base_write_hashes(
        scope=scope,
        snapshot=snapshot,
        version_identities=version_identities,
        available_model_hashes=available_model_hashes,
    )
    graph_nodes: dict[GraphNodeKey, GraphIdentityNode] = _graph_identity_nodes(
        scope=scope,
        version_identities=version_identities,
    )
    write_hashes: dict[GraphNodeKey, str] = build_graph_write_identity_hashes(
        nodes=graph_nodes,
        execution_order=tuple(
            graph_key_for_compiled_resource(resource_type=key.resource_type, name=key.name)
            for key in scope.execution_order
        ),
        selected_keys=frozenset(
            graph_key_for_compiled_resource(resource_type=key.resource_type, name=key.name)
            for key in scope.selected_keys
        ),
        base_identity_hashes=base_hashes,
        compose_identity=compose_native_graph_identity,
    )
    models_by_name: dict[str, CompiledModel] = scope.models_by_name
    model_changes: dict[str, ChangeDetectionResult] = dict(changes.models)
    key: CompiledObjectKey
    for key in scope.execution_order:
        if key.resource_type != CompiledResourceType.MODEL:
            continue
        model: CompiledModel | None = models_by_name.get(key.name)
        if model is None:
            continue
        if key not in scope.selected_keys:
            continue
        local_hash: str | None = version_identities.model_local_hashes.get(model.name)
        if local_hash is None:
            continue
        graph_key: GraphNodeKey = graph_key_for_compiled_resource(
            resource_type=CompiledResourceType.MODEL,
            name=model.name,
        )
        write_hash: str | None = write_hashes.get(graph_key)
        if write_hash is None:
            continue
        change: ChangeDetectionResult | None = model_changes.get(model.name)
        if change is None:
            continue
        model_changes[model.name] = replace(change, fingerprint_version_hash=write_hash)
    return replace(changes, models=model_changes)


def merge_recomputed_model_changes(
    *,
    resolved_actions: PlannerResolvedActions,
    changes: PlannerChangeResults,
) -> PlannerResolvedActions:
    """Patch recomputed model changes into resolved actions, keeping run-despite-unchanged kinds."""

    merged_models: dict[str, ResolvedModelAction] = {}
    model_name: str
    resolved: ResolvedModelAction
    for model_name, resolved in resolved_actions.models.items():
        merged_models[model_name] = replace(
            resolved,
            change=_merged_recomputed_change(
                resolved_change=resolved.change,
                recomputed_change=changes.models.get(model_name),
            ),
        )
    return replace(resolved_actions, models=merged_models)


def _merged_recomputed_change(
    *,
    resolved_change: ChangeDetectionResult,
    recomputed_change: ChangeDetectionResult | None,
) -> ChangeDetectionResult:
    """Prefer the recomputed change but never downgrade RUN_DESPITE_UNCHANGED to NO_CHANGE."""

    if recomputed_change is None:
        return resolved_change
    if (
        resolved_change.change_kind == ChangeKind.RUN_DESPITE_UNCHANGED
        and recomputed_change.change_kind == ChangeKind.NO_CHANGE
    ):
        return replace(
            recomputed_change,
            change_kind=ChangeKind.RUN_DESPITE_UNCHANGED,
            backfill=resolved_change.backfill,
        )
    return recomputed_change


def _graph_identity_nodes(
    *, scope: PlannerScope, version_identities: DirectModelVersionIdentities
) -> dict[GraphNodeKey, GraphIdentityNode]:
    nodes: dict[GraphNodeKey, GraphIdentityNode] = {}
    function_name: str
    function_hash: str
    for function_name, function_hash in version_identities.function_local_hashes.items():
        for resource_type in (CompiledResourceType.UDF, CompiledResourceType.TABLE_FN):
            function_key: GraphNodeKey = graph_key_for_compiled_resource(
                resource_type=resource_type,
                name=function_name,
            )
            nodes[function_key] = GraphIdentityNode(
                key=function_key,
                resource_kind=GraphResourceKind.FUNCTION,
                upstream_keys=tuple(
                    graph_key_for_compiled_resource(
                        resource_type=dep.resource_type,
                        name=dep.name,
                    )
                    for dep in scope.upstream_deps.get(
                        CompiledObjectKey(resource_type=resource_type, name=function_name),
                        (),
                    )
                ),
                local_hash=function_hash,
            )
    seed_name: str
    seed_hash: str
    for seed_name, seed_hash in version_identities.seed_version_hashes.items():
        seed_key: GraphNodeKey = graph_key_for_compiled_resource(
            resource_type=CompiledResourceType.SEED,
            name=seed_name,
        )
        nodes[seed_key] = GraphIdentityNode(
            key=seed_key,
            resource_kind=GraphResourceKind.SEED,
            upstream_keys=(),
            local_hash=seed_hash,
        )
    model: CompiledModel
    for model in scope.models_by_name.values():
        model_key: GraphNodeKey = graph_key_for_compiled_resource(
            resource_type=CompiledResourceType.MODEL,
            name=model.name,
        )
        nodes[model_key] = GraphIdentityNode(
            key=model_key,
            resource_kind=GraphResourceKind.MODEL,
            upstream_keys=tuple(
                graph_key_for_compiled_resource(resource_type=dep.resource_type, name=dep.name)
                for dep in model.deps
            ),
            local_hash=version_identities.model_local_hashes.get(model.name),
        )
    return nodes


def _base_write_hashes(
    *,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    version_identities: DirectModelVersionIdentities,
    available_model_hashes: dict[str, str] | None,
) -> dict[GraphNodeKey, str]:
    hashes: dict[GraphNodeKey, str] = {}
    function_name: str
    function_hash: str
    for function_name, function_hash in version_identities.function_local_hashes.items():
        for resource_type in (CompiledResourceType.UDF, CompiledResourceType.TABLE_FN):
            hashes[
                graph_key_for_compiled_resource(resource_type=resource_type, name=function_name)
            ] = function_hash
    seed_name: str
    seed_hash: str
    for seed_name, seed_hash in _seed_write_hashes(
        scope=scope,
        snapshot=snapshot,
        version_identities=version_identities,
    ).items():
        hashes[
            graph_key_for_compiled_resource(
                resource_type=CompiledResourceType.SEED,
                name=seed_name,
            )
        ] = seed_hash
    model_name: str
    model_hash: str
    for model_name, model_hash in _built_model_hashes(snapshot).items():
        hashes[
            graph_key_for_compiled_resource(
                resource_type=CompiledResourceType.MODEL,
                name=model_name,
            )
        ] = model_hash
    for model_name, model_hash in (available_model_hashes or {}).items():
        hashes[
            graph_key_for_compiled_resource(
                resource_type=CompiledResourceType.MODEL,
                name=model_name,
            )
        ] = model_hash
    return hashes


def _seed_write_hashes(
    *,
    scope: PlannerScope,
    snapshot: WarehouseSnapshot,
    version_identities: DirectModelVersionIdentities,
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    seed_name: str
    expected_hash: str
    for seed_name, expected_hash in version_identities.seed_version_hashes.items():
        seed_key: CompiledObjectKey = CompiledObjectKey(
            resource_type=CompiledResourceType.SEED, name=seed_name
        )
        if seed_key in scope.selected_keys:
            hashes[seed_name] = expected_hash
            continue
        fingerprint: Fingerprint | None = snapshot.fingerprints.seeds.get(seed_name)
        hashes[seed_name] = fingerprint.version_hash if fingerprint is not None else expected_hash
    return hashes


def _built_model_hashes(snapshot: WarehouseSnapshot) -> dict[str, str]:
    return {
        model_name: fingerprint.version_hash
        for model_name, fingerprint in snapshot.fingerprints.models.items()
        if fingerprint.version_hash
    }
