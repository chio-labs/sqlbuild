"""Mixed dbt/SQLBuild model-level lineage selection helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledProject
from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.helpers.graph.core import (
    dbt_model_graph_key,
    dbt_source_graph_key,
    sqlbuild_model_graph_key,
)
from sqlbuild.integrations.dbt.manifest.models import (
    DbtManifestIndex,
    DbtManifestModel,
    DbtManifestSource,
)
from sqlbuild.integrations.dbt.models import (
    DbtCombinedGraph,
    DbtCombinedGraphKey,
    DbtLineageGraph,
    DbtLineageNode,
)
from sqlbuild.integrations.dbt.types import (
    DbtCombinedGraphOwner,
    DbtCombinedGraphResourceType,
    DbtLineageDirection,
)
from sqlbuild.shared.helpers.graph_algorithms import transitive_closure


def select_dbt_lineage_target(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    graph: DbtCombinedGraph,
    target: str,
    direction: DbtLineageDirection,
    depth: int | None,
) -> DbtLineageGraph:
    """Select mixed lineage around one SQLBuild or dbt model target."""

    key: DbtCombinedGraphKey = resolve_dbt_lineage_target(
        project=project,
        manifest=manifest,
        target=target,
    )
    selected: set[DbtCombinedGraphKey] = {key}
    if direction in {DbtLineageDirection.UPSTREAM, DbtLineageDirection.BOTH}:
        selected.update(transitive_closure(start=key, edges=graph.upstream_deps, max_depth=depth))
    if direction in {DbtLineageDirection.DOWNSTREAM, DbtLineageDirection.BOTH}:
        selected.update(transitive_closure(start=key, edges=graph.downstream_deps, max_depth=depth))
    return build_dbt_lineage_graph(
        project=project,
        manifest=manifest,
        upstream_deps=graph.upstream_deps,
        selected_keys=frozenset(selected),
        focus_keys=(key,),
        direction=direction,
    )


def resolve_dbt_lineage_target(
    *, project: CompiledProject, manifest: DbtManifestIndex, target: str
) -> DbtCombinedGraphKey:
    """Resolve a mixed lineage target to an owner-qualified graph key."""

    sqlbuild_names: frozenset[str] = frozenset(model.name for model in project.models)
    if target in sqlbuild_names:
        return sqlbuild_model_graph_key(target)
    if target in manifest.models_by_unique_id:
        return dbt_model_graph_key(target)
    if target in manifest.sources_by_unique_id:
        return dbt_source_graph_key(target)
    matches: tuple[DbtManifestModel, ...] = manifest.models_by_name.get(target, ())
    if len(matches) == 1:
        return dbt_model_graph_key(matches[0].unique_id)
    if len(matches) > 1:
        unique_ids: str = ", ".join(sorted(model.unique_id for model in matches))
        raise DbtInteropArgumentError(
            f"ambiguous dbt lineage target '{target}'",
            code="C330",
            help=f"Use one of these dbt unique IDs: {unique_ids}",
        )
    raise DbtInteropArgumentError(f"unknown dbt lineage target '{target}'", code="C331")


def build_dbt_lineage_graph(
    *,
    project: CompiledProject,
    manifest: DbtManifestIndex,
    upstream_deps: dict[DbtCombinedGraphKey, tuple[DbtCombinedGraphKey, ...]],
    selected_keys: frozenset[DbtCombinedGraphKey],
    focus_keys: tuple[DbtCombinedGraphKey, ...] = (),
    direction: DbtLineageDirection | None = None,
) -> DbtLineageGraph:
    """Build display nodes and selected mixed lineage edges."""

    nodes: tuple[DbtLineageNode, ...] = tuple(
        _build_node(project=project, manifest=manifest, key=key)
        for key in sorted(selected_keys, key=lambda key: key.stable_id)
    )
    selected_edges: list[tuple[DbtCombinedGraphKey, DbtCombinedGraphKey]] = []
    downstream_key: DbtCombinedGraphKey
    for downstream_key in sorted(selected_keys, key=lambda key: key.stable_id):
        upstream_key: DbtCombinedGraphKey
        for upstream_key in upstream_deps.get(downstream_key, ()):
            if upstream_key in selected_keys:
                selected_edges.append((upstream_key, downstream_key))
    return DbtLineageGraph(
        nodes=nodes,
        edges=tuple(selected_edges),
        focus_keys=focus_keys,
        direction=direction,
    )


def _build_node(
    *, project: CompiledProject, manifest: DbtManifestIndex, key: DbtCombinedGraphKey
) -> DbtLineageNode:
    if key.owner == DbtCombinedGraphOwner.SQLBUILD:
        model: CompiledModel
        for model in project.models:
            if model.name == key.name:
                return DbtLineageNode(
                    key=key,
                    label=model.name,
                    qualified_name=model.destination.qualified_name,
                    relative_path=str(model.relative_path),
                )
        return DbtLineageNode(key=key, label=key.name)
    if key.resource_type == DbtCombinedGraphResourceType.MODEL:
        dbt_model: DbtManifestModel | None = manifest.models_by_unique_id.get(key.name)
        if dbt_model is not None:
            return DbtLineageNode(
                key=key,
                label=dbt_model.name,
                qualified_name=dbt_model.relation_name,
                relative_path=_optional_payload_str(dbt_model.payload.get("original_file_path")),
            )
    source: DbtManifestSource | None = manifest.sources_by_unique_id.get(key.name)
    if source is not None:
        return DbtLineageNode(
            key=key,
            label=f"{source.source_name}.{source.name}",
            qualified_name=source.relation_name,
            relative_path=_optional_payload_str(source.payload.get("original_file_path")),
        )
    return DbtLineageNode(key=key, label=key.name)


def _optional_payload_str(value: object | None) -> str | None:
    if isinstance(value, str):
        return value
    return None
