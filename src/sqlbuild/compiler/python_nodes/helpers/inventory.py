"""Inventory helpers for executable Python DAG nodes."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import get_type_hints

from sqlbuild.assets import get_asset_definition
from sqlbuild.checks import get_check_definition
from sqlbuild.compiler.discovery.models import (
    DiscoveredAssetFunction,
    DiscoveredCheckFunction,
    DiscoveredLoaderFunction,
    DiscoveredProjectInputs,
    DiscoveredProvider,
    DiscoveredProviderUsage,
    DiscoveredTaskFunction,
)
from sqlbuild.compiler.python_nodes.helpers.identity import build_python_identity
from sqlbuild.compiler.python_nodes.models import (
    DiscoveredPythonAssetMetadata,
    DiscoveredPythonCheckMetadata,
    DiscoveredPythonLoaderMetadata,
    DiscoveredPythonNode,
    DiscoveredPythonTaskMetadata,
    PythonNodeDependencyEdge,
    PythonNodeGraph,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind
from sqlbuild.loaders import get_loader_definition
from sqlbuild.providers import Provider
from sqlbuild.shared.models import (
    AssetDefinition,
    CheckDefinition,
    LoaderDefinition,
    SqlResourceRef,
    TaskDefinition,
)
from sqlbuild.tasks import get_task_definition


def build_python_node_graph(*, discovered_inputs: DiscoveredProjectInputs) -> PythonNodeGraph:
    """Build the internal executable Python-node graph from discovered project inputs."""

    nodes: tuple[DiscoveredPythonNode, ...] = build_python_nodes(
        loader_functions=discovered_inputs.loader_functions,
        task_functions=discovered_inputs.task_functions,
        asset_functions=discovered_inputs.asset_functions,
        check_functions=discovered_inputs.check_functions,
        providers=discovered_inputs.providers,
    )
    dependency_edges: tuple[PythonNodeDependencyEdge, ...] = build_python_node_dependency_edges(
        nodes=nodes
    )
    return PythonNodeGraph(
        nodes=nodes,
        dependency_edges=dependency_edges,
        upstream_deps=build_python_node_upstream_deps(nodes=nodes, edges=dependency_edges),
        downstream_deps=build_python_node_downstream_deps(nodes=nodes, edges=dependency_edges),
        tag_index=build_python_node_tag_index(nodes=nodes),
        path_index=build_python_node_path_index(nodes=nodes),
        nodes_by_name={node.name: node for node in nodes},
        nodes_by_typed_selector={_typed_selector(node): node for node in nodes},
    )


def build_python_nodes(
    *,
    loader_functions: tuple[DiscoveredLoaderFunction, ...] = (),
    task_functions: tuple[DiscoveredTaskFunction, ...] = (),
    asset_functions: tuple[DiscoveredAssetFunction, ...] = (),
    check_functions: tuple[DiscoveredCheckFunction, ...] = (),
    providers: tuple[DiscoveredProvider, ...] = (),
) -> tuple[DiscoveredPythonNode, ...]:
    """Return the shared internal node view for all executable Python node kinds."""

    nodes: list[DiscoveredPythonNode] = []
    provider_by_name: dict[str, DiscoveredProvider] = {
        discovered_provider.name: discovered_provider for discovered_provider in providers
    }
    loader_function: DiscoveredLoaderFunction
    for loader_function in loader_functions:
        nodes.append(_build_loader_node(loader_function, provider_by_name=provider_by_name))
    task_function: DiscoveredTaskFunction
    for task_function in task_functions:
        nodes.append(_build_task_node(task_function, provider_by_name=provider_by_name))
    asset_function: DiscoveredAssetFunction
    for asset_function in asset_functions:
        nodes.append(_build_asset_node(asset_function, provider_by_name=provider_by_name))
    check_function: DiscoveredCheckFunction
    for check_function in check_functions:
        nodes.append(_build_check_node(check_function, provider_by_name=provider_by_name))
    return tuple(nodes)


def build_python_node_dependency_edges(
    *, nodes: tuple[DiscoveredPythonNode, ...]
) -> tuple[PythonNodeDependencyEdge, ...]:
    """Return dependency edges across loaders, tasks, assets, and checks."""

    node_by_dependency_key: dict[object | tuple[str, str], DiscoveredPythonNode] = {
        node.function: node for node in nodes
    }
    node: DiscoveredPythonNode
    for node in nodes:
        node_by_dependency_key[("name", node.name)] = node

    edges: list[PythonNodeDependencyEdge] = []
    for node in nodes:
        dependency: Callable[..., object] | SqlResourceRef
        for dependency in node.depends_on:
            if isinstance(dependency, SqlResourceRef):
                continue
            upstream_node: DiscoveredPythonNode | None = node_by_dependency_key.get(
                _python_node_dependency_key(dependency)
            )
            if upstream_node is None:
                continue
            edges.append(
                PythonNodeDependencyEdge(
                    upstream_name=upstream_node.name,
                    downstream_name=node.name,
                    upstream_function=upstream_node.function,
                    downstream_function=node.function,
                )
            )
    return tuple(edges)


def build_python_node_upstream_deps(
    *, nodes: tuple[DiscoveredPythonNode, ...], edges: tuple[PythonNodeDependencyEdge, ...]
) -> dict[str, tuple[str, ...]]:
    """Return upstream Python-node dependency names keyed by downstream node name."""

    upstream: dict[str, list[str]] = {node.name: [] for node in nodes}
    edge: PythonNodeDependencyEdge
    for edge in edges:
        upstream.setdefault(edge.downstream_name, []).append(edge.upstream_name)
        upstream.setdefault(edge.upstream_name, [])
    return {name: tuple(values) for name, values in upstream.items()}


def build_python_node_downstream_deps(
    *, nodes: tuple[DiscoveredPythonNode, ...], edges: tuple[PythonNodeDependencyEdge, ...]
) -> dict[str, tuple[str, ...]]:
    """Return downstream Python-node dependency names keyed by upstream node name."""

    downstream: dict[str, list[str]] = {node.name: [] for node in nodes}
    edge: PythonNodeDependencyEdge
    for edge in edges:
        downstream.setdefault(edge.upstream_name, []).append(edge.downstream_name)
        downstream.setdefault(edge.downstream_name, [])
    return {name: tuple(values) for name, values in downstream.items()}


def build_python_node_tag_index(
    *, nodes: tuple[DiscoveredPythonNode, ...]
) -> dict[str, frozenset[str]]:
    """Build a tag-to-node-name lookup for tagged Python nodes."""

    index: dict[str, set[str]] = {}
    node: DiscoveredPythonNode
    for node in nodes:
        tag: str
        for tag in node.tags:
            index.setdefault(tag, set()).add(node.name)
    return {tag: frozenset(names) for tag, names in index.items()}


def build_python_node_path_index(*, nodes: tuple[DiscoveredPythonNode, ...]) -> dict[str, str]:
    """Build a node-name-to-folder lookup from discovered Python node relative paths."""

    return {node.name: node.relative_path.parent.as_posix() for node in nodes}


def _build_loader_node(
    loader: DiscoveredLoaderFunction, *, provider_by_name: dict[str, DiscoveredProvider]
) -> DiscoveredPythonNode:
    return DiscoveredPythonNode(
        kind=PythonNodeKind.LOADER,
        file_path=loader.file_path,
        relative_path=loader.relative_path,
        name=loader.name,
        function=loader.function,
        depends_on=loader.depends_on,
        sql_deps=_sql_deps(loader.depends_on),
        provider_usages=_provider_usages(
            function=loader.function, provider_by_name=provider_by_name
        ),
        loader=DiscoveredPythonLoaderMetadata(
            destination=loader.destination,
            write_strategy=loader.write_strategy,
            cursor_column=loader.cursor_column,
            unique_key=loader.unique_key,
            columns=loader.columns,
            contract=loader.contract,
            connection_mode=loader.connection_mode,
        ),
        identity=build_python_identity(
            node_type=PythonNodeKind.LOADER.value,
            node_name=loader.name,
            function=loader.function,
            project_dir=loader.file_path.parent,
            decorator_config={
                "contract": loader.contract,
                "cursor_column": loader.cursor_column,
                "destination": loader.destination,
                "unique_key": loader.unique_key,
                "write_strategy": loader.write_strategy.value
                if loader.write_strategy is not None
                else None,
            },
        ),
    )


def _build_task_node(
    task: DiscoveredTaskFunction, *, provider_by_name: dict[str, DiscoveredProvider]
) -> DiscoveredPythonNode:
    return DiscoveredPythonNode(
        kind=PythonNodeKind.TASK,
        file_path=task.file_path,
        relative_path=task.relative_path,
        name=task.name,
        function=task.function,
        depends_on=task.depends_on,
        sql_deps=_sql_deps(task.depends_on),
        tags=task.tags,
        group=task.group,
        description=task.description,
        meta=task.meta,
        provider_usages=_provider_usages(function=task.function, provider_by_name=provider_by_name),
        task=DiscoveredPythonTaskMetadata(retry=task.retry),
        identity=build_python_identity(
            node_type=PythonNodeKind.TASK.value,
            node_name=task.name,
            function=task.function,
            project_dir=task.file_path.parent,
            decorator_config={
                "description": task.description,
                "group": task.group,
                "meta": task.meta,
                "tags": task.tags,
            },
        ),
    )


def _build_asset_node(
    asset: DiscoveredAssetFunction, *, provider_by_name: dict[str, DiscoveredProvider]
) -> DiscoveredPythonNode:
    return DiscoveredPythonNode(
        kind=PythonNodeKind.ASSET,
        file_path=asset.file_path,
        relative_path=asset.relative_path,
        name=asset.name,
        function=asset.function,
        depends_on=asset.depends_on,
        sql_deps=_sql_deps(asset.depends_on),
        tags=asset.tags,
        group=asset.group,
        description=asset.description,
        meta=asset.meta,
        provider_usages=_provider_usages(
            function=asset.function, provider_by_name=provider_by_name
        ),
        asset=DiscoveredPythonAssetMetadata(
            columns=asset.columns,
            column_lineage=asset.column_lineage,
            retry=asset.retry,
        ),
        identity=build_python_identity(
            node_type=PythonNodeKind.ASSET.value,
            node_name=asset.name,
            function=asset.function,
            project_dir=asset.file_path.parent,
            decorator_config={
                "columns": asset.columns,
                "column_lineage": asset.column_lineage,
                "description": asset.description,
                "group": asset.group,
                "meta": asset.meta,
                "tags": asset.tags,
            },
        ),
    )


def _build_check_node(
    check: DiscoveredCheckFunction, *, provider_by_name: dict[str, DiscoveredProvider]
) -> DiscoveredPythonNode:
    return DiscoveredPythonNode(
        kind=PythonNodeKind.CHECK,
        file_path=check.file_path,
        relative_path=check.relative_path,
        name=check.name,
        function=check.function,
        depends_on=check.depends_on,
        sql_deps=_sql_deps(check.depends_on),
        tags=check.tags,
        group=check.group,
        description=check.description,
        meta=check.meta,
        provider_usages=_provider_usages(
            function=check.function, provider_by_name=provider_by_name
        ),
        check=DiscoveredPythonCheckMetadata(severity=check.severity),
        identity=build_python_identity(
            node_type=PythonNodeKind.CHECK.value,
            node_name=check.name,
            function=check.function,
            project_dir=check.file_path.parent,
            decorator_config={
                "description": check.description,
                "group": check.group,
                "meta": check.meta,
                "severity": check.severity.value,
                "tags": check.tags,
            },
        ),
    )


def _provider_usages(
    *, function: Callable[..., object], provider_by_name: dict[str, DiscoveredProvider]
) -> tuple[DiscoveredProviderUsage, ...]:
    usages: list[DiscoveredProviderUsage] = []
    type_hints: dict[str, object] = get_type_hints(function)
    parameter: inspect.Parameter
    for parameter in inspect.signature(function).parameters.values():
        discovered_provider: DiscoveredProvider | None = provider_by_name.get(parameter.name)
        if discovered_provider is None:
            continue
        annotation: object = type_hints.get(parameter.name, parameter.annotation)
        annotation_class_name: str | None = None
        annotation_module: str | None = None
        if isinstance(annotation, type) and issubclass(annotation, Provider):
            annotation_class_name = annotation.__name__
            annotation_module = annotation.__module__
        usages.append(
            DiscoveredProviderUsage(
                provider_name=discovered_provider.name,
                parameter_name=parameter.name,
                annotation_class_name=annotation_class_name,
                annotation_module=annotation_module,
            )
        )
    return tuple(usages)


def _python_node_dependency_key(dependency: object) -> object | tuple[str, str]:
    loader_definition: LoaderDefinition | None = (
        get_loader_definition(dependency) if callable(dependency) else None
    )
    if loader_definition is not None:
        return ("name", loader_definition.name)
    task_definition: TaskDefinition | None = (
        get_task_definition(dependency) if callable(dependency) else None
    )
    if task_definition is not None:
        return ("name", task_definition.name)
    asset_definition: AssetDefinition | None = (
        get_asset_definition(dependency) if callable(dependency) else None
    )
    if asset_definition is not None:
        return ("name", asset_definition.name)
    check_definition: CheckDefinition | None = (
        get_check_definition(dependency) if callable(dependency) else None
    )
    if check_definition is not None:
        return ("name", check_definition.name)
    return dependency


def _sql_deps(
    dependencies: tuple[Callable[..., object] | SqlResourceRef, ...],
) -> tuple[SqlResourceRef, ...]:
    return tuple(
        dependency for dependency in dependencies if isinstance(dependency, SqlResourceRef)
    )


def _typed_selector(node: DiscoveredPythonNode) -> str:
    return f"{node.kind.value}:{node.name}"
