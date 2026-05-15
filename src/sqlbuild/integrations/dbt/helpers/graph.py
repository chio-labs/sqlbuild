"""Combined dbt and SQLBuild graph helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.integrations.dbt.helpers.manifest import resolve_dbt_manifest_model
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex, DbtManifestModel
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCombinedGraphKey,
)
from sqlbuild.integrations.dbt.types import DbtCombinedGraphOwner, DbtCombinedGraphResourceType
from sqlbuild.shared.types import SqlReferenceKind


def build_dbt_combined_graph(
    *, manifest: DbtManifestIndex, project: CompiledProject
) -> DbtCombinedGraph:
    """Build a downstream-only combined graph from dbt manifest and SQLBuild compile."""

    upstream: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]] = {}
    _add_dbt_model_edges(upstream=upstream, manifest=manifest)
    _add_sqlbuild_model_edges(upstream=upstream, manifest=manifest, project=project)

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


def build_combined_downstream_deps(
    upstream: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
) -> dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]]:
    """Return downstream edges keyed by upstream combined graph key."""

    downstream: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]] = {}
    key: DbtCombinedGraphKey
    for key in upstream:
        downstream.setdefault(key, [])
    dep_keys: tuple[DbtCombinedGraphKey, ...]
    for key, dep_keys in upstream.items():
        dep_key: DbtCombinedGraphKey
        for dep_key in dep_keys:
            downstream.setdefault(dep_key, []).append(key)
    return {key: _sorted_keys(values) for key, values in downstream.items()}


def expand_combined_upstream(
    key: DbtCombinedGraphKey,
    upstream: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
) -> frozenset[DbtCombinedGraphKey]:
    """Return all transitive upstream combined graph keys."""

    return _expand(key=key, edges=upstream)


def expand_combined_downstream(
    key: DbtCombinedGraphKey,
    downstream: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
) -> frozenset[DbtCombinedGraphKey]:
    """Return all transitive downstream combined graph keys."""

    return _expand(key=key, edges=downstream)


def _add_dbt_model_edges(
    *, upstream: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]], manifest: DbtManifestIndex
) -> None:
    model: DbtManifestModel
    for model in manifest.models_by_unique_id.values():
        key: DbtCombinedGraphKey = dbt_model_graph_key(model.unique_id)
        upstream.setdefault(key, [])
        dep_unique_id: str
        for dep_unique_id in model.depends_on_nodes:
            if dep_unique_id not in manifest.models_by_unique_id:
                continue
            upstream[key].append(dbt_model_graph_key(dep_unique_id))


def _add_sqlbuild_model_edges(
    *,
    upstream: dict[DbtCombinedGraphKey, list[DbtCombinedGraphKey]],
    manifest: DbtManifestIndex,
    project: CompiledProject,
) -> None:
    sqlbuild_model_names: frozenset[str] = frozenset(model.name for model in project.models)
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

        reference: CompileSqlReference
        for reference in model.references:
            if reference.ref_kind != SqlReferenceKind.DBT_REF:
                continue
            dbt_model: DbtManifestModel = resolve_dbt_manifest_model(
                manifest=manifest,
                package_name=reference.ref_package,
                name=reference.ref_name,
            )
            upstream[key].append(dbt_model_graph_key(dbt_model.unique_id))


def _expand(
    *,
    key: DbtCombinedGraphKey,
    edges: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
) -> frozenset[DbtCombinedGraphKey]:
    visited: set[DbtCombinedGraphKey] = set()
    stack: list[DbtCombinedGraphKey] = [key]
    while stack:
        current: DbtCombinedGraphKey = stack.pop()
        neighbor: DbtCombinedGraphKey
        for neighbor in edges.get(current, ()):  # pragma: no branch
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return frozenset(visited)


def _sorted_keys(keys: list[DbtCombinedGraphKey]) -> tuple[DbtCombinedGraphKey, ...]:
    return tuple(sorted(keys, key=lambda key: key.stable_id))
