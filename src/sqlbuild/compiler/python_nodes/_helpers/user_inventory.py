"""Python-node inventory over loaded user functions: signatures, providers and dependencies."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Protocol, get_type_hints

from sqlbuild._native import python_node_graph_indexes
from sqlbuild.compiler.discovery.models import (
    DiscoveredAssetFunction,
    DiscoveredCheckFunction,
    DiscoveredLoaderFunction,
    DiscoveredProjectInputs,
    DiscoveredProvider,
    DiscoveredProviderUsage,
    DiscoveredTaskFunction,
)
from sqlbuild.compiler.python_nodes._helpers.identity import build_python_identity
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
from sqlbuild.provider.classes.provider import Provider
from sqlbuild.python_nodes.main.read_asset_definition import read_asset_definition
from sqlbuild.python_nodes.main.read_check_definition import read_check_definition
from sqlbuild.python_nodes.main.read_loader_definition import read_loader_definition
from sqlbuild.python_nodes.main.read_task_definition import read_task_definition
from sqlbuild.python_nodes.models import (
    AssetDefinition,
    CheckDefinition,
    LoaderDefinition,
    SqlResourceRef,
    TaskDefinition,
)


def build_python_node_graph(*, discovered_inputs: DiscoveredProjectInputs) -> PythonNodeGraph:
    """Build the internal executable Python-node graph from discovered project inputs."""

    nodes: tuple[DiscoveredPythonNode, ...] = build_python_nodes(
        loader_functions=discovered_inputs.loader_functions,
        task_functions=discovered_inputs.task_functions,
        asset_functions=discovered_inputs.asset_functions,
        check_functions=discovered_inputs.check_functions,
        providers=discovered_inputs.providers,
    )
    edges, upstream, downstream, tags, paths = python_node_graph_indexes(
        [
            (node.name, node.tags, node.relative_path.as_posix(), upstream_names)
            for node, upstream_names in zip(nodes, _upstream_node_names(nodes), strict=True)
        ]
    )
    return PythonNodeGraph(
        nodes=nodes,
        dependency_edges=tuple(
            PythonNodeDependencyEdge(upstream_name=upstream_name, downstream_name=downstream_name)
            for upstream_name, downstream_name in edges
        ),
        upstream_deps={name: tuple(names) for name, names in upstream},
        downstream_deps={name: tuple(names) for name, names in downstream},
        tag_index={tag: frozenset(names) for tag, names in tags},
        path_index=dict(paths),
        nodes_by_name={node.name: node for node in nodes},
        nodes_by_typed_selector={f"{node.kind.value}:{node.name}": node for node in nodes},
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
        nodes.append(_build_loader_node(loader=loader_function, provider_by_name=provider_by_name))
    task_function: DiscoveredTaskFunction
    for task_function in task_functions:
        nodes.append(_build_task_node(task=task_function, provider_by_name=provider_by_name))
    asset_function: DiscoveredAssetFunction
    for asset_function in asset_functions:
        nodes.append(_build_asset_node(asset=asset_function, provider_by_name=provider_by_name))
    check_function: DiscoveredCheckFunction
    for check_function in check_functions:
        nodes.append(_build_check_node(check=check_function, provider_by_name=provider_by_name))
    return tuple(nodes)


def _upstream_node_names(nodes: tuple[DiscoveredPythonNode, ...]) -> list[list[str]]:
    """Each node's Python-node dependencies, resolving live callables to node names."""

    node_by_dependency_key: dict[object | tuple[str, str], DiscoveredPythonNode] = {
        node.function: node for node in nodes
    }
    node: DiscoveredPythonNode
    for node in nodes:
        node_by_dependency_key[("name", node.name)] = node
    upstream_names: list[list[str]] = []
    for node in nodes:
        names: list[str] = []
        dependency: Callable[..., object] | SqlResourceRef
        for dependency in node.depends_on:
            if isinstance(dependency, SqlResourceRef):
                continue
            upstream_node: DiscoveredPythonNode | None = node_by_dependency_key.get(
                _python_node_dependency_key(dependency)
            )
            if upstream_node is not None:
                names.append(upstream_node.name)
        upstream_names.append(names)
    return upstream_names


class _DiscoveredPythonFunction(Protocol):
    @property
    def file_path(self) -> Path: ...

    @property
    def relative_path(self) -> Path: ...

    @property
    def name(self) -> str: ...

    @property
    def function(self) -> Callable[..., object]: ...

    @property
    def depends_on(self) -> tuple[Callable[..., object] | SqlResourceRef, ...]: ...


class _DocumentedPythonFunction(_DiscoveredPythonFunction, Protocol):
    @property
    def tags(self) -> tuple[str, ...]: ...

    @property
    def group(self) -> str | None: ...

    @property
    def description(self) -> str | None: ...

    @property
    def meta(self) -> dict[str, object] | None: ...


def _build_loader_node(
    *, loader: DiscoveredLoaderFunction, provider_by_name: dict[str, DiscoveredProvider]
) -> DiscoveredPythonNode:
    return replace(
        _build_python_node(
            kind=PythonNodeKind.LOADER,
            discovered=loader,
            provider_by_name=provider_by_name,
            decorator_config={
                "columns": loader.columns,
                "contract": loader.contract,
                "cursor_column": loader.cursor_column,
                "destination": loader.destination,
                "unique_key": loader.unique_key,
                "write_strategy": loader.write_strategy.value
                if loader.write_strategy is not None
                else None,
            },
        ),
        description=loader.description,
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


def _build_task_node(
    *, task: DiscoveredTaskFunction, provider_by_name: dict[str, DiscoveredProvider]
) -> DiscoveredPythonNode:
    return replace(
        _build_documented_python_node(
            kind=PythonNodeKind.TASK,
            discovered=task,
            provider_by_name=provider_by_name,
            decorator_config={},
        ),
        task=DiscoveredPythonTaskMetadata(retry=task.retry),
    )


def _build_asset_node(
    *, asset: DiscoveredAssetFunction, provider_by_name: dict[str, DiscoveredProvider]
) -> DiscoveredPythonNode:
    return replace(
        _build_documented_python_node(
            kind=PythonNodeKind.ASSET,
            discovered=asset,
            provider_by_name=provider_by_name,
            decorator_config={"columns": asset.columns, "column_lineage": asset.column_lineage},
        ),
        asset=DiscoveredPythonAssetMetadata(
            columns=asset.columns,
            column_lineage=asset.column_lineage,
            retry=asset.retry,
        ),
    )


def _build_check_node(
    *, check: DiscoveredCheckFunction, provider_by_name: dict[str, DiscoveredProvider]
) -> DiscoveredPythonNode:
    return replace(
        _build_documented_python_node(
            kind=PythonNodeKind.CHECK,
            discovered=check,
            provider_by_name=provider_by_name,
            decorator_config={"severity": check.severity.value},
        ),
        check=DiscoveredPythonCheckMetadata(severity=check.severity),
    )


def _build_documented_python_node(
    *,
    kind: PythonNodeKind,
    discovered: _DocumentedPythonFunction,
    provider_by_name: dict[str, DiscoveredProvider],
    decorator_config: dict[str, object],
) -> DiscoveredPythonNode:
    return replace(
        _build_python_node(
            kind=kind,
            discovered=discovered,
            provider_by_name=provider_by_name,
            decorator_config={
                **decorator_config,
                "description": discovered.description,
                "group": discovered.group,
                "meta": discovered.meta,
                "tags": discovered.tags,
            },
        ),
        tags=discovered.tags,
        group=discovered.group,
        description=discovered.description,
        meta=discovered.meta,
    )


def _build_python_node(
    *,
    kind: PythonNodeKind,
    discovered: _DiscoveredPythonFunction,
    provider_by_name: dict[str, DiscoveredProvider],
    decorator_config: dict[str, object],
) -> DiscoveredPythonNode:
    """Build the kind-independent node view; decorator_config is exactly the identity input."""

    return DiscoveredPythonNode(
        kind=kind,
        file_path=discovered.file_path,
        relative_path=discovered.relative_path,
        name=discovered.name,
        function=discovered.function,
        depends_on=discovered.depends_on,
        sql_deps=_sql_deps(discovered.depends_on),
        provider_usages=_provider_usages(
            function=discovered.function, provider_by_name=provider_by_name
        ),
        identity=build_python_identity(
            node_type=kind.value,
            node_name=discovered.name,
            function=discovered.function,
            project_dir=discovered.file_path.parent,
            decorator_config=decorator_config,
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
        read_loader_definition(dependency) if callable(dependency) else None
    )
    if loader_definition is not None:
        return ("name", loader_definition.name)
    task_definition: TaskDefinition | None = (
        read_task_definition(dependency) if callable(dependency) else None
    )
    if task_definition is not None:
        return ("name", task_definition.name)
    asset_definition: AssetDefinition | None = (
        read_asset_definition(dependency) if callable(dependency) else None
    )
    if asset_definition is not None:
        return ("name", asset_definition.name)
    check_definition: CheckDefinition | None = (
        read_check_definition(dependency) if callable(dependency) else None
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
