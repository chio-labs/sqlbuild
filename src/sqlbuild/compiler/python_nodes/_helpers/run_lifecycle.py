"""Lifecycle classification for build-style SQL/Python selections."""

from __future__ import annotations

from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.graph.main.transitive_closure import transitive_closure
from sqlbuild.compiler.python_nodes.models import (
    DiscoveredPythonLoaderMetadata,
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind


def build_python_sql_run_lifecycle_plan(
    *, selection: PythonSqlRunSelection, python_graph: PythonNodeGraph
) -> PythonSqlRunLifecyclePlan:
    """Classify selected run nodes into lifecycle-aware execution regions."""

    selected_python_names: frozenset[str] = selection.python_node_names
    selected_loader_names: frozenset[str] = frozenset(
        name
        for name in selected_python_names
        if python_graph.nodes_by_name[name].kind == PythonNodeKind.LOADER
        if not _is_external_loader(node_name=name, python_graph=python_graph)
    )
    ingress_upstream_names: set[str] = set()
    for loader_name in selected_loader_names:
        for upstream_name in transitive_closure(
            start=loader_name, edges=python_graph.upstream_deps
        ):
            if upstream_name not in selected_python_names:
                continue
            if python_graph.nodes_by_name[upstream_name].kind in {
                PythonNodeKind.TASK,
                PythonNodeKind.ASSET,
                PythonNodeKind.LOADER,
            }:
                ingress_upstream_names.add(upstream_name)
    ingress_names: frozenset[str] = selected_loader_names | frozenset(ingress_upstream_names)
    read_side_names: frozenset[str] = frozenset(
        name
        for name in selected_python_names - ingress_names
        if python_graph.nodes_by_name[name].kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}
    )
    return PythonSqlRunLifecyclePlan(
        ingress_python_node_names=ingress_names,
        ingress_loader_names=selected_loader_names,
        read_side_sql_keys=selection.sql_keys,
        read_side_python_node_names=read_side_names,
    )


def _is_external_loader(*, node_name: str, python_graph: PythonNodeGraph) -> bool:
    loader: DiscoveredPythonLoaderMetadata | None = python_graph.nodes_by_name[node_name].loader
    return loader is not None and loader.connection_mode == LoaderConnectionMode.EXTERNAL
