"""dbt combined graph projections into neutral planner graph keys."""

from __future__ import annotations

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.planner.models import GraphNodeKey
from sqlbuild.integrations.dbt.helpers.graph.core import dbt_model_graph_key
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import DbtCombinedGraph, DbtCombinedGraphKey
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
)


def dbt_graph_node_key(unique_id: str) -> GraphNodeKey:
    """Return the neutral planner graph key for one dbt unique ID."""

    return GraphNodeKey(node_type=NODE_TYPE_DBT, node_name=unique_id)


def dbt_source_graph_node_key(unique_id: str) -> GraphNodeKey:
    """Return the neutral planner graph key for one dbt source unique ID."""

    return GraphNodeKey(node_type=CompiledResourceType.SOURCE.value, node_name=unique_id)


def sqlbuild_model_graph_node_key(name: str) -> GraphNodeKey:
    """Return the neutral planner graph key for one SQLBuild model name."""

    return GraphNodeKey(node_type=CompiledResourceType.MODEL.value, node_name=name)


def dbt_graph_node_upstream_deps(
    *, graph: DbtCombinedGraph
) -> dict[GraphNodeKey, tuple[GraphNodeKey, ...]]:
    """Project dbt-owned combined graph edges to neutral graph node edges."""

    return {
        dbt_graph_node_key(key.name): tuple(
            dbt_graph_node_key(upstream_key.name)
            for upstream_key in upstream_keys
            if upstream_key.owner == DbtCombinedGraphOwner.DBT
        )
        for key, upstream_keys in graph.upstream_deps.items()
        if key.owner == DbtCombinedGraphOwner.DBT
    }


def dbt_identity_upstream_keys(
    *, unique_id: str, manifest: DbtManifestIndex, graph: DbtCombinedGraph | None
) -> tuple[GraphNodeKey, ...]:
    """Return dbt model/seed upstream keys that contribute to identity hashing."""

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
