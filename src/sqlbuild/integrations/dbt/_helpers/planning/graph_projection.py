"""dbt combined graph projections into neutral planner graph keys."""

from __future__ import annotations

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.constants import NODE_TYPE_DBT
from sqlbuild.compiler.planner.models import GraphNodeKey, SelectionStalenessNodeKey
from sqlbuild.integrations.dbt._helpers.graph.core import dbt_model_graph_key
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

    projected: dict[GraphNodeKey, tuple[GraphNodeKey, ...]] = {}
    for key, upstream_keys in graph.upstream_deps.items():
        if key.owner != DbtCombinedGraphOwner.DBT:
            continue
        dbt_upstreams: list[GraphNodeKey] = []
        for upstream_key in upstream_keys:
            if upstream_key.owner == DbtCombinedGraphOwner.DBT:
                dbt_upstreams.append(dbt_graph_node_key(upstream_key.name))
        projected[dbt_graph_node_key(key.name)] = tuple(dbt_upstreams)
    return projected


def dbt_selection_staleness_upstream_deps(
    *, manifest: DbtManifestIndex, graph: DbtCombinedGraph
) -> dict[SelectionStalenessNodeKey, tuple[SelectionStalenessNodeKey, ...]]:
    """Project dbt-owned combined graph edges to neutral selection-staleness edges."""

    upstream_deps: dict[SelectionStalenessNodeKey, tuple[SelectionStalenessNodeKey, ...]] = {}
    key: DbtCombinedGraphKey
    upstream_keys: tuple[DbtCombinedGraphKey, ...]
    for key, upstream_keys in graph.upstream_deps.items():
        neutral_key: SelectionStalenessNodeKey | None = dbt_selection_staleness_key(
            manifest=manifest, key=key
        )
        if neutral_key is None:
            continue
        upstream_deps[neutral_key] = tuple(
            neutral_upstream_key
            for upstream_key in upstream_keys
            if (
                neutral_upstream_key := dbt_selection_staleness_key(
                    manifest=manifest, key=upstream_key
                )
            )
            is not None
        )
    return upstream_deps


def dbt_selection_staleness_key(
    *, manifest: DbtManifestIndex, key: DbtCombinedGraphKey
) -> SelectionStalenessNodeKey | None:
    """Return the neutral selection-staleness key for one dbt-owned graph node."""

    if key.owner != DbtCombinedGraphOwner.DBT:
        return None
    if key.resource_type == DbtCombinedGraphResourceType.MODEL:
        if (model := manifest.models_by_unique_id.get(key.name)) is None:
            return None
        return SelectionStalenessNodeKey(resource_type="model", name=model.name)
    if key.resource_type == DbtCombinedGraphResourceType.SOURCE:
        if (seed := manifest.seeds_by_unique_id.get(key.name)) is not None:
            return SelectionStalenessNodeKey(resource_type="seed", name=seed.name)
        if (source := manifest.sources_by_unique_id.get(key.name)) is not None:
            return SelectionStalenessNodeKey(resource_type="source", name=source.name)
    return None


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
