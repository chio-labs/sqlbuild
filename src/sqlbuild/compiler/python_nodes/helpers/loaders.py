"""Loader adapters for internal Python-node models."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.python_nodes.models import (
    DiscoveredPythonLoaderMetadata,
    DiscoveredPythonNode,
    PythonNodeDependencyEdge,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.shared.models import SqlResourceRef


def build_python_loader_node(*, loader: DiscoveredLoaderFunction) -> DiscoveredPythonNode:
    """Return an internal Python-node view of an existing discovered loader."""

    return DiscoveredPythonNode(
        kind=PythonNodeKind.LOADER,
        file_path=loader.file_path,
        relative_path=loader.relative_path,
        name=loader.name,
        function=loader.function,
        depends_on=loader.depends_on,
        loader=DiscoveredPythonLoaderMetadata(
            destination=loader.destination,
            write_strategy=loader.write_strategy,
            cursor_column=loader.cursor_column,
            unique_key=loader.unique_key,
            columns=loader.columns,
            contract=loader.contract,
            connection_mode=loader.connection_mode,
        ),
    )


def build_python_loader_nodes(
    *, loaders: tuple[DiscoveredLoaderFunction, ...]
) -> tuple[DiscoveredPythonNode, ...]:
    """Return internal Python-node views of existing discovered loaders."""

    return tuple(build_python_loader_node(loader=loader) for loader in loaders)


def build_python_loader_dependency_edges(
    *, loaders: tuple[DiscoveredLoaderFunction, ...]
) -> tuple[PythonNodeDependencyEdge, ...]:
    """Return internal dependency edges between existing discovered loaders."""

    loader_name_by_function: dict[object, str] = {
        loader.function: loader.name for loader in loaders
    }
    edges: list[PythonNodeDependencyEdge] = []
    loader: DiscoveredLoaderFunction
    for loader in loaders:
        dependency: Callable[..., object] | SqlResourceRef
        for dependency in loader.depends_on:
            if isinstance(dependency, SqlResourceRef):
                continue
            upstream_name: str | None = loader_name_by_function.get(dependency)
            if upstream_name is None:
                continue
            edges.append(
                PythonNodeDependencyEdge(
                    upstream_name=upstream_name,
                    downstream_name=loader.name,
                    upstream_function=dependency,
                    downstream_function=loader.function,
                )
            )
    return tuple(edges)
