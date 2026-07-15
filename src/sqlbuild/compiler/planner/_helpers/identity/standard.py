"""Direct planner model version identity helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledFunction, CompiledModel, CompiledSeed
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.identity.hashing import (
    compose_native_graph_identity,
    graph_key_for_compiled_resource,
)
from sqlbuild.compiler.planner._helpers.identity.seed import build_seed_identity
from sqlbuild.compiler.planner.main.identity.graph_identity import (
    build_expected_graph_identity_hashes,
)
from sqlbuild.compiler.planner.main.identity.version_identity_function_hashes import (
    build_function_local_hashes,
)
from sqlbuild.compiler.planner.main.identity.version_identity_local_hash import (
    build_model_local_identity_hash,
)
from sqlbuild.compiler.planner.main.identity.version_identity_model_metadata import (
    build_model_version_identity_metadata_json,
)
from sqlbuild.compiler.planner.models import (
    GraphIdentityNode,
    GraphNodeKey,
    PlannerScope,
    StandardModelVersionIdentities,
)
from sqlbuild.compiler.planner.types import GraphResourceKind


def build_standard_model_version_identities(
    *,
    functions: tuple[CompiledFunction, ...],
    seeds: tuple[CompiledSeed, ...] = (),
    scope: PlannerScope,
    source_version_hashes: dict[str, str] | None = None,
) -> StandardModelVersionIdentities:
    """Compute current standard model identities from code and upstream identities."""

    function_local_hashes: dict[str, str] = build_function_local_hashes(functions=functions)
    seed_version_hashes: dict[str, str] = {}
    seed_metadata_jsons: dict[str, str] = {}
    seed: CompiledSeed
    for seed in seeds:
        seed_hash: str
        seed_metadata_json: str
        seed_hash, seed_metadata_json = build_seed_identity(seed)
        seed_version_hashes[seed.name] = seed_hash
        seed_metadata_jsons[seed.name] = seed_metadata_json
    model_metadata_jsons: dict[str, str] = {}
    model_local_hashes: dict[str, str] = {}
    graph_nodes: dict[GraphNodeKey, GraphIdentityNode] = {}
    function: CompiledFunction
    for function in functions:
        function_hash: str | None = function_local_hashes.get(function.name)
        if function_hash is None:
            continue
        function_key: GraphNodeKey = graph_key_for_compiled_resource(
            resource_type=function.key.resource_type,
            name=function.name,
        )
        graph_nodes[function_key] = GraphIdentityNode(
            key=function_key,
            resource_kind=GraphResourceKind.FUNCTION,
            upstream_keys=(),
            local_hash=function_hash,
        )
    seed_name: str
    for seed_name, seed_hash in seed_version_hashes.items():
        seed_key: GraphNodeKey = graph_key_for_compiled_resource(
            resource_type=CompiledResourceType.SEED,
            name=seed_name,
        )
        graph_nodes[seed_key] = GraphIdentityNode(
            key=seed_key,
            resource_kind=GraphResourceKind.SEED,
            upstream_keys=(),
            local_hash=seed_hash,
        )
    source_hashes: dict[str, str] = source_version_hashes or {}
    source_name: str
    source_hash: str
    for source_name, source_hash in source_hashes.items():
        source_key: GraphNodeKey = graph_key_for_compiled_resource(
            resource_type=CompiledResourceType.SOURCE,
            name=source_name,
        )
        graph_nodes[source_key] = GraphIdentityNode(
            key=source_key,
            resource_kind=GraphResourceKind.SOURCE,
            upstream_keys=(),
            local_hash=source_hash,
        )

    key: object
    for key in scope.execution_order:
        if not hasattr(key, "resource_type") or key.resource_type != CompiledResourceType.MODEL:
            continue
        model: CompiledModel | None = scope.models_by_name.get(key.name)
        if model is None:
            continue
        metadata_json: str = build_model_version_identity_metadata_json(
            model=model,
            function_local_hashes=function_local_hashes,
        )
        model_metadata_jsons[model.name] = metadata_json
        local_hash: str = build_model_local_identity_hash(
            query_sql=model.query_sql,
            metadata_json=metadata_json,
        )
        model_local_hashes[model.name] = local_hash
        model_key: GraphNodeKey = graph_key_for_compiled_resource(
            resource_type=CompiledResourceType.MODEL,
            name=model.name,
        )
        graph_nodes[model_key] = GraphIdentityNode(
            key=model_key,
            resource_kind=GraphResourceKind.MODEL,
            upstream_keys=tuple(
                graph_key_for_compiled_resource(resource_type=dep.resource_type, name=dep.name)
                for dep in model.deps
            ),
            local_hash=local_hash,
        )

    graph_hashes: dict[GraphNodeKey, str | None] = build_expected_graph_identity_hashes(
        nodes=graph_nodes,
        execution_order=tuple(
            graph_key_for_compiled_resource(resource_type=key.resource_type, name=key.name)
            for key in scope.execution_order
            if hasattr(key, "resource_type")
        ),
        compose_identity=compose_native_graph_identity,
    )
    model_version_hashes: dict[str, str] = {**function_local_hashes, **seed_version_hashes}
    model_name: str
    for model_name in model_local_hashes:
        model_hash: str | None = graph_hashes.get(
            graph_key_for_compiled_resource(
                resource_type=CompiledResourceType.MODEL,
                name=model_name,
            )
        )
        if model_hash is not None:
            model_version_hashes[model_name] = model_hash

    return StandardModelVersionIdentities(
        function_local_hashes=function_local_hashes,
        seed_version_hashes=seed_version_hashes,
        seed_metadata_jsons=seed_metadata_jsons,
        model_metadata_jsons=model_metadata_jsons,
        model_local_hashes=model_local_hashes,
        model_version_hashes=model_version_hashes,
    )
