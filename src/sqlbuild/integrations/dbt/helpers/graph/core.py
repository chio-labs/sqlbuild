"""Combined dbt and SQLBuild graph helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.graph.main.invert_edges import invert_edges
from sqlbuild.compiler.graph.main.transitive_closure import transitive_closure
from sqlbuild.integrations.dbt.constants import DBT_MATERIALIZATION_VIEW
from sqlbuild.integrations.dbt.helpers.manifest.core import (
    dbt_manifest_model_materialization,
)
from sqlbuild.integrations.dbt.helpers.manifest.sqlbuild_refs import (
    resolve_sqlbuild_model_dbt_refs,
)
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSource,
)
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCombinedGraphKey,
)
from sqlbuild.integrations.dbt.types import DbtCombinedGraphOwner, DbtCombinedGraphResourceType

_SQLBUILD_VIEW_MATERIALIZATION: str = "view"


def build_dbt_combined_graph(
    *, manifest: DbtManifestIndex, project: CompiledProject
) -> DbtCombinedGraph:
    """Build a downstream-only combined graph from dbt manifest and SQLBuild compile."""

    upstream: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]] = {}
    upstream = _add_dbt_model_edges(upstream=upstream, manifest=manifest)
    upstream = _add_sqlbuild_model_edges(upstream=upstream, manifest=manifest, project=project)

    normalized_upstream: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]] = {
        key: _sorted_keys(deps) for key, deps in upstream.items()
    }
    downstream: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]] = (
        build_combined_downstream_deps(normalized_upstream)
    )
    return DbtCombinedGraph(
        nodes=frozenset(normalized_upstream),
        upstream_deps=normalized_upstream,
        downstream_deps=downstream,
    )


def dbt_model_graph_key(unique_id: str) -> DbtCombinedGraphKey:
    """Return the combined graph key for one dbt model unique_id."""

    return DbtCombinedGraphKey(
        owner=DbtCombinedGraphOwner.DBT,
        resource_type=DbtCombinedGraphResourceType.MODEL,
        name=unique_id,
    )


def sqlbuild_model_graph_key(model_name: str) -> DbtCombinedGraphKey:
    """Return the combined graph key for one SQLBuild model name."""

    return DbtCombinedGraphKey(
        owner=DbtCombinedGraphOwner.SQLBUILD,
        resource_type=DbtCombinedGraphResourceType.MODEL,
        name=model_name,
    )


def dbt_source_graph_key(unique_id: str) -> DbtCombinedGraphKey:
    """Return the combined graph key for one dbt source unique_id."""

    return DbtCombinedGraphKey(
        owner=DbtCombinedGraphOwner.DBT,
        resource_type=DbtCombinedGraphResourceType.SOURCE,
        name=unique_id,
    )


def combined_graph_node_is_clonable(
    *, key: DbtCombinedGraphKey, manifest: DbtManifestIndex
) -> bool:
    """Return whether a combined graph node is a model or seed (not a true source)."""

    if key.resource_type == DbtCombinedGraphResourceType.MODEL:
        return True
    return key.name in manifest.seeds_by_unique_id


def combined_graph_node_is_view(
    *,
    key: DbtCombinedGraphKey,
    manifest: DbtManifestIndex,
    project: CompiledProject,
) -> bool:
    """Return whether a combined graph node is materialized as a view."""

    if key.owner == DbtCombinedGraphOwner.DBT:
        model: DbtManifestModel | None = manifest.models_by_unique_id.get(key.name)
        if model is None:
            return False
        return dbt_manifest_model_materialization(model=model) == DBT_MATERIALIZATION_VIEW
    sqlbuild_model: CompiledModel | None = next(
        (model for model in project.models if model.name == key.name), None
    )
    if sqlbuild_model is None:
        return False
    materialized: object | None = sqlbuild_model.config.values.get(
        "materialized", _SQLBUILD_VIEW_MATERIALIZATION
    )
    return str(materialized).lower() == _SQLBUILD_VIEW_MATERIALIZATION


def build_combined_downstream_deps(
    upstream: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
) -> dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]]:
    """Return downstream edges keyed by upstream combined graph key."""

    inverted: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]] = invert_edges(
        edges=upstream
    )
    return {key: _sorted_keys(list(values)) for key, values in inverted.items()}


def expand_combined_upstream(
    *,
    key: DbtCombinedGraphKey,
    upstream: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
) -> frozenset[DbtCombinedGraphKey]:
    """Return all transitive upstream combined graph keys."""

    return transitive_closure(start=key, edges=upstream)


def expand_combined_downstream(
    *,
    key: DbtCombinedGraphKey,
    downstream: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
) -> frozenset[DbtCombinedGraphKey]:
    """Return all transitive downstream combined graph keys."""

    return transitive_closure(start=key, edges=downstream)


def _add_dbt_model_edges(
    *, upstream: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]], manifest: DbtManifestIndex
) -> dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]]:
    model: DbtManifestModel
    for model in manifest.models_by_unique_id.values():
        key: DbtCombinedGraphKey = dbt_model_graph_key(model.unique_id)
        upstream.setdefault(key, [])
        dep_unique_id: str
        for dep_unique_id in model.depends_on_nodes:
            if dep_unique_id in manifest.models_by_unique_id:
                upstream[key].append(dbt_model_graph_key(dep_unique_id))
            if dep_unique_id in manifest.sources_by_unique_id:
                source: DbtManifestSource = manifest.sources_by_unique_id[dep_unique_id]
                source_key: DbtCombinedGraphKey = dbt_source_graph_key(source.unique_id)
                upstream.setdefault(source_key, [])
                upstream[key].append(source_key)
            if dep_unique_id in manifest.seeds_by_unique_id:
                seed_key: DbtCombinedGraphKey = dbt_source_graph_key(dep_unique_id)
                upstream.setdefault(seed_key, [])
                upstream[key].append(seed_key)
    return upstream


def _add_sqlbuild_model_edges(
    *,
    upstream: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]],
    manifest: DbtManifestIndex,
    project: CompiledProject,
) -> dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]]:
    sqlbuild_model_names: frozenset[str] = frozenset(model.name for model in project.models)
    dbt_refs_by_model_name: dict[str, list[DbtManifestModel]] = {}
    sqlbuild_model: CompiledModel
    dbt_model: DbtManifestModel
    for sqlbuild_model, dbt_model in resolve_sqlbuild_model_dbt_refs(
        project=project,
        manifest=manifest,
    ):
        dbt_refs_by_model_name.setdefault(sqlbuild_model.name, []).append(dbt_model)
    model: CompiledModel
    for model in project.models:
        key: DbtCombinedGraphKey = sqlbuild_model_graph_key(model.name)
        upstream.setdefault(key, [])
        dep_key: CompiledObjectKey
        for dep_key in model.deps:
            if dep_key.resource_type != CompiledResourceType.MODEL:
                continue
            if dep_key.name not in sqlbuild_model_names:
                continue
            upstream[key].append(sqlbuild_model_graph_key(dep_key.name))

        for dbt_model in dbt_refs_by_model_name.get(model.name, ()):
            upstream[key].append(dbt_model_graph_key(dbt_model.unique_id))
    return upstream


def _sorted_keys(keys: list[DbtCombinedGraphKey]) -> tuple[DbtCombinedGraphKey, ...]:
    return tuple(sorted(keys, key=lambda key: key.stable_id))
