"""Cross-file discovery validation, run natively over the facts of one discovery."""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterable
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
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind
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
type _Named = tuple[str, str]


class _NamedResource(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def relative_path(self) -> Path: ...


class _ResourceFile(Protocol):
    @property
    def file_path(self) -> Path: ...
    @property
    def relative_path(self) -> Path: ...


class _NodeDefinition(Protocol):
    @property
    def name(self) -> str: ...


_UNREADABLE_TAG: str = "unreadable"
_CSV_ERROR_TAG: str = "csv"
_CSV_SETTING_TAG: str = "csv_setting"
_DEFINITION_READERS: tuple[Callable[[Callable[..., object]], _NodeDefinition | None], ...] = (
    read_loader_definition,
    read_task_definition,
    read_asset_definition,
    read_check_definition,
)


def validate_discovered_inputs(discovered_inputs: DiscoveredProjectInputs) -> None:
    """Validate cross-file conflicts across discovered project inputs."""

    payload: tuple[object, ...] | None = _native.validate_discovered_inputs(
        _facts(discovered_inputs)
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
    if tag == _CSV_SETTING_TAG:
        raise TypeError(str(payload[1]))
    raise native_failure(payload)


def _facts(inputs: DiscoveredProjectInputs) -> dict[str, object]:
    nodes: tuple[tuple[str, _PythonNode], ...] = (
        *(("loader", node) for node in inputs.loader_functions),
        *(("task", node) for node in inputs.task_functions),
        *(("asset", node) for node in inputs.asset_functions),
        *(("check", node) for node in inputs.check_functions),
    )
    owners: dict[object, int] = {node.function: index for index, (_, node) in enumerate(nodes)}
    return {
        "models": [
            (
                model.file_path.stem,
                str(model.relative_path),
                _named_paths((*model.enum_declarations, *model.constant_declarations)),
            )
            for model in inputs.model_files
        ],
        "sql_functions": _stems(inputs.sql_function_files),
        "python_functions": _stems(inputs.python_function_files),
        "sql_hooks": _named_paths(inputs.sql_hook_files),
        "seeds": [
            (seed.file_path.stem, str(seed.relative_path), str(seed.file_path))
            for seed in inputs.seed_files
        ],
        "schemas": [
            (
                str(schema.relative_path),
                [entry.name for entry in schema.model_entries],
                [
                    {
                        "name": entry.name,
                        "columns": [column.name for column in entry.columns],
                        "delimiter": entry.csv_settings.delimiter,
                        "quotechar": entry.csv_settings.quotechar,
                        "escapechar": entry.csv_settings.escapechar,
                        "doublequote": entry.csv_settings.doublequote,
                        "skipinitialspace": entry.csv_settings.skipinitialspace,
                    }
                    for entry in schema.seed_entries
                ],
            )
            for schema in inputs.schema_files
        ],
        "sources": [
            (
                str(source.relative_path),
                [
                    {
                        "name": entry.name,
                        "managed": entry.managed,
                        "loader": entry.loader,
                        "integration_kind": (
                            None
                            if entry.integration_loader is None
                            else entry.integration_loader.kind
                        ),
                    }
                    for entry in source.source_entries
                ],
            )
            for source in inputs.source_files
        ],
        "tests": [
            (
                test.relative_path.stem,
                str(test.relative_path),
                [(block.name, [case.name for case in block.cases]) for block in test.blocks],
            )
            for test in inputs.test_files
        ],
        "scenarios": _named_paths(inputs.scenario_files),
        "audits": [
            (
                (audit.relative_path.stem, str(audit.relative_path)),
                audit.declaration_kind is DeclarationKind.AUDIT,
                [block.name for block in audit.blocks],
            )
            for audit in inputs.audit_files
        ],
        "declaration_files": [
            (file.scope_kind is ScopeKind.PRIVATE, _named_paths(file.declarations))
            for file in (*inputs.enum_files, *inputs.constant_files)
        ],
        "model_schemas": _named_paths(
            declaration
            for schema in inputs.model_schema_files
            for declaration in schema.declarations
        ),
        "materializations": _named_paths(inputs.materialization_files),
        "nodes": [_node(kind=kind, node=node, owners=owners) for kind, node in nodes],
        "hook_functions": _named_paths(inputs.hook_functions),
        "event_exporters": _named_paths(inputs.event_exporters),
        "providers": _named_paths(inputs.providers),
        "path_default_keys": list(inputs.project_config.path_defaults),
    }


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


def _named_paths(resources: Iterable[_NamedResource]) -> list[_Named]:
    return [(resource.name, str(resource.relative_path)) for resource in resources]


def _stems(files: Iterable[_ResourceFile]) -> list[_Named]:
    return [(file.file_path.stem, str(file.relative_path)) for file in files]
