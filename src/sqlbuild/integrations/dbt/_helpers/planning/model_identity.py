"""dbt graph identity adapter helpers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

from sqlbuild.compiler.planner.main.identity.graph_write_identity import (
    build_graph_write_identity_hashes,
)
from sqlbuild.compiler.planner.models import GraphIdentityNode, GraphNodeKey
from sqlbuild.compiler.planner.types import GraphResourceKind
from sqlbuild.integrations.dbt._helpers.planning.graph_projection import (
    dbt_graph_node_key,
    dbt_identity_upstream_keys,
)
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSeed,
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
            upstream_keys=dbt_identity_upstream_keys(
                unique_id=model.unique_id,
                manifest=manifest,
                graph=graph,
            ),
            local_hash=model.node_checksum,
        )
    return nodes


def dbt_graph_identity_execution_order(*, manifest: DbtManifestIndex) -> tuple[GraphNodeKey, ...]:
    return tuple(dbt_graph_node_key(unique_id) for unique_id in manifest.models_by_unique_id)


def build_dbt_write_identity_hashes(
    *,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph | None,
    run_unique_ids: frozenset[str],
    expected_version_hash_by_unique_id: dict[str, str | None],
    previous_version_hash_by_unique_id: dict[str, str] | None = None,
) -> dict[GraphNodeKey, str]:
    """Compose the version hashes recorded for dbt nodes written in one run."""

    previous_version_hash_by_unique_id = previous_version_hash_by_unique_id or {}
    nodes: dict[GraphNodeKey, GraphIdentityNode] = build_dbt_graph_identity_nodes(
        manifest=manifest,
        graph=graph,
    )
    base_identity_hashes: dict[GraphNodeKey, str] = {
        dbt_graph_node_key(unique_id): version_hash
        for unique_id, version_hash in previous_version_hash_by_unique_id.items()
    }
    unique_id: str
    version_hash: str | None
    for unique_id, version_hash in expected_version_hash_by_unique_id.items():
        if version_hash is not None:
            base_identity_hashes.setdefault(dbt_graph_node_key(unique_id), version_hash)
    seed_unique_id: str
    seed: DbtManifestSeed
    for seed_unique_id, seed in manifest.seeds_by_unique_id.items():
        if seed.identity_hash is not None:
            base_identity_hashes[dbt_graph_node_key(seed_unique_id)] = seed.identity_hash
    return build_graph_write_identity_hashes(
        nodes=nodes,
        execution_order=dbt_graph_identity_execution_order(manifest=manifest),
        selected_keys=frozenset(dbt_graph_node_key(unique_id) for unique_id in run_unique_ids),
        base_identity_hashes=base_identity_hashes,
        compose_identity=compose_dbt_graph_version_hash,
    )


def compose_dbt_graph_version_hash(
    *, local_hash: str, upstream_hashes: tuple[tuple[GraphNodeKey, str], ...]
) -> str:
    return compose_dbt_version_hash(
        own_hash=local_hash,
        upstream_hashes=tuple(
            (key.node_name, upstream_hash) for key, upstream_hash in upstream_hashes
        ),
    )
