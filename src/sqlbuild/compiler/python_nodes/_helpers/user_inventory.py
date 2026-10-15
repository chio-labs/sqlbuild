"""Python-node facts read from loaded user functions: identities, providers and dependencies."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path
from typing import get_type_hints

from sqlbuild.compiler.discovery.models import DiscoveredProvider, DiscoveredProviderUsage
from sqlbuild.compiler.python_nodes._helpers.identity import build_python_identity
from sqlbuild.compiler.python_nodes.models import PythonNodeIdentity
from sqlbuild.provider.classes.provider import Provider
from sqlbuild.python_nodes.main.read_asset_definition import read_asset_definition
from sqlbuild.python_nodes.main.read_check_definition import read_check_definition
from sqlbuild.python_nodes.main.read_loader_definition import read_loader_definition
from sqlbuild.python_nodes.main.read_task_definition import read_task_definition
from sqlbuild.python_nodes.models import (
    AssetDefinition,
    CheckDefinition,
    LoaderDefinition,
    TaskDefinition,
)


def python_node_user_facts(
    *,
    kind: str,
    name: str,
    function: Callable[..., object],
    file_path: Path,
    provider_by_name: dict[str, DiscoveredProvider],
    decorator_config: dict[str, object],
) -> tuple[tuple[DiscoveredProviderUsage, ...], PythonNodeIdentity]:
    """Read provider parameters and the identity of one loaded user node function."""

    return (
        provider_usages(function=function, provider_by_name=provider_by_name),
        build_python_identity(
            node_type=kind,
            node_name=name,
            function=function,
            project_dir=file_path.parent,
            decorator_config=decorator_config,
        ),
    )


def provider_usages(
    *, function: Callable[..., object], provider_by_name: dict[str, DiscoveredProvider]
) -> tuple[DiscoveredProviderUsage, ...]:
    """Provider parameters of one loaded user function and their annotation classes."""

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


def python_node_dependency_key(dependency: object) -> object | tuple[str, str]:
    """The node name a decorated dependency declares, or the dependency itself."""

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
