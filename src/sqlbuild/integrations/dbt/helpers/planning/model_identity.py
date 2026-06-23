"""dbt graph identity adapter helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.planner.models import GraphIdentityNode, GraphNodeKey
from sqlbuild.compiler.planner.types import GraphResourceKind
from sqlbuild.integrations.dbt.helpers.graph.core import dbt_model_graph_key
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSeed,
)
from sqlbuild.integrations.dbt.models import DbtCombinedGraph, DbtCombinedGraphKey
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
)


def compose_dbt_version_hash(*, own_hash: str, upstream_hashes: Sequence[tuple[str, str]]) -> str:
    """Compose a dbt model version hash from its own checksum and upstream identities."""

    if not upstream_hashes:
        return own_hash
    payload: str = json.dumps(
        {"own": own_hash, "upstream": sorted(upstream_hashes)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def build_dbt_graph_identity_nodes(
    *, manifest: DbtManifestIndex, graph: DbtCombinedGraph | None
) -> dict[GraphNodeKey, GraphIdentityNode]:
    nodes: dict[GraphNodeKey, GraphIdentityNode] = {}
    seed: DbtManifestSeed
    for seed in manifest.seeds_by_unique_id.values():
        key: GraphNodeKey = dbt_graph_node_key(seed.unique_id)
        nodes[key] = GraphIdentityNode(
            key=key,
            resource_kind=GraphResourceKind.SEED,
            upstream_keys=(),
            local_hash=seed.identity_hash,
        )
    model: DbtManifestModel
    for model in manifest.models_by_unique_id.values():
        key = dbt_graph_node_key(model.unique_id)
        nodes[key] = GraphIdentityNode(
            key=key,
            resource_kind=GraphResourceKind.MODEL,
            upstream_keys=_dbt_graph_identity_upstream_keys(
                unique_id=model.unique_id,
                manifest=manifest,
                graph=graph,
            ),
            local_hash=model.node_checksum,
        )
    return nodes


def dbt_graph_identity_execution_order(*, manifest: DbtManifestIndex) -> tuple[GraphNodeKey, ...]:
    return tuple(dbt_graph_node_key(unique_id) for unique_id in manifest.models_by_unique_id)


def dbt_graph_node_key(unique_id: str) -> GraphNodeKey:
    return GraphNodeKey(node_type=NODE_TYPE_DBT, node_name=unique_id)


def compose_dbt_graph_version_hash(
    own_hash: str, upstream_hashes: tuple[tuple[GraphNodeKey, str], ...]
) -> str:
    return compose_dbt_version_hash(
        own_hash=own_hash,
        upstream_hashes=tuple(
            (key.node_name, upstream_hash) for key, upstream_hash in upstream_hashes
        ),
    )


def _dbt_graph_identity_upstream_keys(
    *, unique_id: str, manifest: DbtManifestIndex, graph: DbtCombinedGraph | None
) -> tuple[GraphNodeKey, ...]:
    if graph is None:
        return ()
    upstream_keys: list[GraphNodeKey] = []
    key: DbtCombinedGraphKey
    for key in graph.upstream_deps.get(dbt_model_graph_key(unique_id), ()):
        if key.owner != DbtCombinedGraphOwner.DBT:
            continue
        if key.resource_type == DbtCombinedGraphResourceType.MODEL:
            upstream_keys.append(dbt_graph_node_key(key.name))
        elif (
            key.resource_type == DbtCombinedGraphResourceType.SOURCE
            and key.name in manifest.seeds_by_unique_id
        ):
            upstream_keys.append(dbt_graph_node_key(key.name))
    return tuple(upstream_keys)
