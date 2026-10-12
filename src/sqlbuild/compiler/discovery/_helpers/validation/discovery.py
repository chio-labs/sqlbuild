"""Cross-file discovery validation, run natively over the facts of one discovery."""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery._helpers.native.payloads import native_failure, native_read_error
from sqlbuild.compiler.discovery.models import (
    DiscoveredAssetFunction,
    DiscoveredCheckFunction,
    DiscoveredLoaderFunction,
    DiscoveredProjectInputs,
    DiscoveredTaskFunction,
)
from sqlbuild.python_nodes.main.read_asset_definition import read_asset_definition
from sqlbuild.python_nodes.main.read_check_definition import read_check_definition
from sqlbuild.python_nodes.main.read_loader_definition import read_loader_definition
from sqlbuild.python_nodes.main.read_task_definition import read_task_definition
from sqlbuild.python_nodes.models import SqlResourceRef

type _PythonNode = (
    DiscoveredLoaderFunction
    | DiscoveredTaskFunction
    | DiscoveredAssetFunction
    | DiscoveredCheckFunction
)


class _NodeDefinition(Protocol):
    @property
    def name(self) -> str: ...


_UNREADABLE_TAG: str = "unreadable"
_CSV_ERROR_TAG: str = "csv"
_CSV_DIALECT_TAG: str = "csv_dialect"
_CSV_DIALECT_ERRORS: dict[str, type[Exception]] = {"TypeError": TypeError, "ValueError": ValueError}
_DEFINITION_READERS: tuple[Callable[[Callable[..., object]], _NodeDefinition | None], ...] = (
    read_loader_definition,
    read_task_definition,
    read_asset_definition,
    read_check_definition,
)


def validate_discovered_inputs(discovered_inputs: DiscoveredProjectInputs) -> None:
    """Validate cross-file conflicts across discovered project inputs."""

    payload: tuple[object, ...] | None = _native.discovered_inputs_failure(
        discovered_inputs, _nodes(discovered_inputs)
    )
    if payload is None:
        return
    tag: object = payload[0]
    if tag == _UNREADABLE_TAG:
        raise native_read_error(
            payload=cast(tuple[object, ...], payload[2]), file_path=Path(str(payload[1]))
        )
    if tag == _CSV_ERROR_TAG:
        raise csv.Error(str(payload[1]))
    if tag == _CSV_DIALECT_TAG:
        raise _CSV_DIALECT_ERRORS[str(payload[1])](str(payload[2]))
    raise native_failure(payload)


def _nodes(inputs: DiscoveredProjectInputs) -> list[dict[str, object]]:
    nodes: tuple[tuple[str, _PythonNode], ...] = (
        *(("loader", node) for node in inputs.loader_functions),
        *(("task", node) for node in inputs.task_functions),
        *(("asset", node) for node in inputs.asset_functions),
        *(("check", node) for node in inputs.check_functions),
    )
    owners: dict[object, int] = {node.function: index for index, (_, node) in enumerate(nodes)}
    return [_node(kind=kind, node=node, owners=owners) for kind, node in nodes]


def _node(*, kind: str, node: _PythonNode, owners: dict[object, int]) -> dict[str, object]:
    return {
        "kind": kind,
        "name": node.name,
        "path": str(node.relative_path),
        "decorator_config": isinstance(node, DiscoveredLoaderFunction)
        and _loader_has_decorator_config(node),
        "depends_on": [
            (dependency.name, None, None)
            if isinstance(dependency, SqlResourceRef)
            else (None, owners.get(dependency), _decorated_name(dependency))
            for dependency in node.depends_on
        ],
    }


def _loader_has_decorator_config(loader_function: DiscoveredLoaderFunction) -> bool:
    return any(
        (
            loader_function.destination is not None,
            loader_function.write_strategy is not None,
            loader_function.cursor_column is not None,
            bool(loader_function.unique_key),
            bool(loader_function.columns),
            loader_function.contract is not None,
        )
    )


def _decorated_name(dependency: object) -> str | None:
    if not callable(dependency):
        return None
    for read_definition in _DEFINITION_READERS:
        definition: _NodeDefinition | None = read_definition(dependency)
        if definition is not None:
            return definition.name
    return None
