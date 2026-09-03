"""Cross-file discovery validation helpers."""

from __future__ import annotations

import csv
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.integrations.loaders import integration_loader_name
from sqlbuild.compiler.discovery._helpers.validation.identities import (
    validate_discovered_resource_identities,
)
from sqlbuild.compiler.discovery.constants import CURRENT_DIRECTORY_PATH, RESERVED_MODEL_NAMES
from sqlbuild.compiler.discovery.exceptions import DiscoveryConflictError, SeedDiscoveryError
from sqlbuild.compiler.discovery.models import (
    DiscoveredAssetFunction,
    DiscoveredCheckFunction,
    DiscoveredHookFunction,
    DiscoveredLoaderFunction,
    DiscoveredProjectInputs,
    DiscoveredProvider,
    DiscoveredPythonFunctionFile,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlHookFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredTaskFunction,
)
from sqlbuild.compiler.path_defaults.main._select import select_path_default
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
from sqlbuild.spec.contracts.models import SchemaModelEntry, SchemaSeedEntry, SourceEntry


def validate_discovered_inputs(discovered_inputs: DiscoveredProjectInputs) -> None:
    """Validate cross-file conflicts across discovered project inputs."""

    validate_discovered_resource_identities(discovered_inputs)
    _validate_unique_model_file_names(discovered_inputs.model_files)
    _validate_unique_scenario_file_names(discovered_inputs.scenario_files)
    _validate_unique_source_names(discovered_inputs.source_files)
    _validate_unique_loader_names(discovered_inputs.loader_functions)
    _validate_unique_python_node_names(
        loader_functions=discovered_inputs.loader_functions,
        task_functions=discovered_inputs.task_functions,
        asset_functions=discovered_inputs.asset_functions,
        check_functions=discovered_inputs.check_functions,
    )
    _validate_source_loader_name_collisions(
        source_files=discovered_inputs.source_files,
        loader_functions=discovered_inputs.loader_functions,
    )
    _validate_loader_dependencies(discovered_inputs.loader_functions)
    _validate_python_node_dependencies(
        loader_functions=discovered_inputs.loader_functions,
        task_functions=discovered_inputs.task_functions,
        asset_functions=discovered_inputs.asset_functions,
    )
    _validate_check_dependencies(
        loader_functions=discovered_inputs.loader_functions,
        task_functions=discovered_inputs.task_functions,
        asset_functions=discovered_inputs.asset_functions,
        check_functions=discovered_inputs.check_functions,
    )
    _validate_source_loader_references(
        source_files=discovered_inputs.source_files,
        loader_functions=discovered_inputs.loader_functions,
    )
    _validate_terminal_loader_config_ownership(
        source_files=discovered_inputs.source_files,
        loader_functions=discovered_inputs.loader_functions,
    )
    _validate_unique_schema_model_names(discovered_inputs.schema_files)
    _validate_unique_schema_seed_names(discovered_inputs.schema_files)
    _validate_unique_logical_relation_names(
        model_files=discovered_inputs.model_files,
        source_files=discovered_inputs.source_files,
        schema_files=discovered_inputs.schema_files,
    )
    _validate_declared_seed_files(
        schema_files=discovered_inputs.schema_files,
        seed_files=discovered_inputs.seed_files,
    )
    _validate_unique_project_resource_names(discovered_inputs)
    _validate_path_defaults_match_models(
        path_defaults=discovered_inputs.project_config.path_defaults,
        model_files=discovered_inputs.model_files,
    )


def _validate_unique_model_file_names(model_files: tuple[DiscoveredSqlModelFile, ...]) -> None:
    seen_names: dict[str, str] = {}
    model_file: DiscoveredSqlModelFile
    for model_file in model_files:
        model_name: str = model_file.file_path.stem
        if model_name in RESERVED_MODEL_NAMES:
            raise DiscoveryConflictError(
                f"Model name '{model_name}' in {model_file.relative_path} is reserved "
                "by SQLBuild for compiled output structure"
            )
        existing_path: str | None = seen_names.get(model_name)
        if existing_path is not None:
            raise DiscoveryConflictError(
                f"Duplicate model file name found for '{model_name}' in "
                f"{existing_path} and {model_file.relative_path}"
            )
        seen_names[model_name] = str(model_file.relative_path)


def _validate_unique_scenario_file_names(
    scenario_files: tuple[DiscoveredSqlScenarioFile, ...],
) -> None:
    seen_names: dict[str, str] = {}
    scenario_file: DiscoveredSqlScenarioFile
    for scenario_file in scenario_files:
        existing_path: str | None = seen_names.get(scenario_file.name)
        if existing_path is not None:
            raise DiscoveryConflictError(
                f"Duplicate scenario file name found for '{scenario_file.name}' in "
                f"{existing_path} and {scenario_file.relative_path}"
            )
        seen_names[scenario_file.name] = str(scenario_file.relative_path)


def _validate_unique_source_names(source_files: tuple[DiscoveredSourceFile, ...]) -> None:
    seen_names: dict[str, str] = {}
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            existing_path: str | None = seen_names.get(source_entry.name)
            if existing_path is not None:
                raise DiscoveryConflictError(
                    "Duplicate source declaration found for "
                    f"'{source_entry.name}' in {existing_path} and {source_file.relative_path}"
                )
            seen_names[source_entry.name] = str(source_file.relative_path)


def _validate_unique_loader_names(loader_functions: tuple[DiscoveredLoaderFunction, ...]) -> None:
    seen_names: dict[str, str] = {}
    loader_function: DiscoveredLoaderFunction
    for loader_function in loader_functions:
        existing_path: str | None = seen_names.get(loader_function.name)
        if existing_path is not None:
            raise DiscoveryConflictError(
                f"Duplicate source loader found for '{loader_function.name}' in "
                f"{existing_path} and {loader_function.relative_path}"
            )
        seen_names[loader_function.name] = str(loader_function.relative_path)


def _validate_unique_python_node_names(
    *,
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    task_functions: tuple[DiscoveredTaskFunction, ...],
    asset_functions: tuple[DiscoveredAssetFunction, ...],
    check_functions: tuple[DiscoveredCheckFunction, ...],
) -> None:
    seen_names: dict[str, str] = {}
    for nodes in (
        loader_functions,
        task_functions,
        asset_functions,
        check_functions,
    ):
        for node in nodes:
            existing_path: str | None = seen_names.get(node.name)
            if existing_path is not None:
                raise DiscoveryConflictError(
                    f"Duplicate Python node found for '{node.name}' in "
                    f"{existing_path} and {node.relative_path}; loader, task, asset, and check "
                    "names must be globally unique"
                )
            seen_names[node.name] = str(node.relative_path)


def _validate_source_loader_name_collisions(
    *,
    source_files: tuple[DiscoveredSourceFile, ...],
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
) -> None:
    loader_paths_by_name: dict[str, str] = {
        loader.name: str(loader.relative_path) for loader in loader_functions
    }
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            loader_path: str | None = loader_paths_by_name.get(source_entry.name)
            if loader_path is None:
                continue
            if source_entry.managed and source_entry.loader == source_entry.name:
                continue
            raise DiscoveryConflictError(
                f"Source '{source_entry.name}' in {source_file.relative_path} conflicts with "
                f"loader '{source_entry.name}' in {loader_path}; source and loader names must "
                "be globally unique unless the source is managed"
            )


def _validate_source_loader_references(
    *,
    source_files: tuple[DiscoveredSourceFile, ...],
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
) -> None:
    loader_names: frozenset[str] = frozenset(loader.name for loader in loader_functions)
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            expected_loader: str | None = source_entry.name
            if source_entry.integration_loader is not None:
                expected_loader = integration_loader_name(
                    kind=source_entry.integration_loader.kind,
                    source_name=source_entry.name,
                )
            if source_entry.managed and source_entry.loader != expected_loader:
                raise DiscoveryConflictError(
                    f"Managed source '{source_entry.name}' in {source_file.relative_path} must "
                    f"use terminal loader '{expected_loader}'"
                )
            if source_entry.managed and expected_loader not in loader_names:
                raise DiscoveryConflictError(
                    f"Managed source '{source_entry.name}' in {source_file.relative_path} "
                    f"requires loader '{expected_loader}'"
                )
            if source_entry.loader is None or source_entry.loader in loader_names:
                continue
            raise DiscoveryConflictError(
                f"Source '{source_entry.name}' in {source_file.relative_path} references "
                f"unknown loader '{source_entry.loader}'"
            )


def _validate_terminal_loader_config_ownership(
    *,
    source_files: tuple[DiscoveredSourceFile, ...],
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
) -> None:
    loader_by_name: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in loader_functions
    }
    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            if source_entry.loader is None:
                continue
            loader_function: DiscoveredLoaderFunction | None = loader_by_name.get(
                source_entry.loader
            )
            if loader_function is None or not _loader_has_decorator_config(loader_function):
                continue
            raise DiscoveryConflictError(
                f"Source '{source_entry.name}' references loader '{source_entry.loader}', "
                "but terminal source loader write and schema config must be declared in "
                "source YAML, not the @loader decorator"
            )


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


def _validate_loader_dependencies(loader_functions: tuple[DiscoveredLoaderFunction, ...]) -> None:
    loader_by_function: dict[object, DiscoveredLoaderFunction] = {
        loader.function: loader for loader in loader_functions
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(
        *,
        loader_function: DiscoveredLoaderFunction,
        path: tuple[str, ...],
        visiting_names: set[str],
        visited_names: set[str],
    ) -> tuple[set[str], set[str]]:
        if loader_function.name in visited_names:
            return visiting_names, visited_names
        if loader_function.name in visiting_names:
            cycle_path: str = " -> ".join((*path, loader_function.name))
            raise DiscoveryConflictError(f"Loader dependency cycle detected: {cycle_path}")
        visiting_names = visiting_names | {loader_function.name}
        dependency: object
        for dependency in loader_function.depends_on:
            if dependency in loader_by_function:
                visiting_names, visited_names = visit(
                    loader_function=loader_by_function[dependency],
                    path=(*path, loader_function.name),
                    visiting_names=visiting_names,
                    visited_names=visited_names,
                )
        visiting_names = visiting_names - {loader_function.name}
        visited_names = visited_names | {loader_function.name}
        return visiting_names, visited_names

    for loader_function in loader_functions:
        visiting, visited = visit(
            loader_function=loader_function,
            path=(),
            visiting_names=visiting,
            visited_names=visited,
        )


def _validate_python_node_dependencies(
    *,
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    task_functions: tuple[DiscoveredTaskFunction, ...],
    asset_functions: tuple[DiscoveredAssetFunction, ...],
) -> None:
    nodes: tuple[
        DiscoveredLoaderFunction | DiscoveredTaskFunction | DiscoveredAssetFunction, ...
    ] = (
        *loader_functions,
        *task_functions,
        *asset_functions,
    )
    node_by_dependency_key: dict[
        object | tuple[str, str],
        DiscoveredLoaderFunction | DiscoveredTaskFunction | DiscoveredAssetFunction,
    ] = {node.function: node for node in nodes}
    for node in nodes:
        node_by_dependency_key[("name", node.name)] = node
    node: DiscoveredLoaderFunction | DiscoveredTaskFunction | DiscoveredAssetFunction
    for node in nodes:
        dependency: object
        for dependency in node.depends_on:
            if isinstance(dependency, SqlResourceRef):
                if isinstance(node, DiscoveredLoaderFunction):
                    raise DiscoveryConflictError(
                        f"Loader '{node.name}' depends on SQL resource "
                        f"'{dependency.name}'; loaders "
                        "may depend on Python loader/task/asset functions only"
                    )
                continue
            if _python_node_dependency_key(dependency) not in node_by_dependency_key:
                if isinstance(node, DiscoveredLoaderFunction):
                    raise DiscoveryConflictError(
                        f"Loader '{node.name}' depends on an unknown loader"
                    )
                raise DiscoveryConflictError(
                    f"Python node '{node.name}' depends on an unknown Python node; "
                    "use function references to decorated loaders, tasks, or assets"
                )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(
        *,
        current: DiscoveredLoaderFunction | DiscoveredTaskFunction | DiscoveredAssetFunction,
        path: tuple[str, ...],
        visiting_names: set[str],
        visited_names: set[str],
    ) -> tuple[set[str], set[str]]:
        if current.name in visited_names:
            return visiting_names, visited_names
        if current.name in visiting_names:
            cycle_path: str = " -> ".join((*path, current.name))
            raise DiscoveryConflictError(f"Python node dependency cycle detected: {cycle_path}")
        visiting_names = visiting_names | {current.name}
        dependency: object
        for dependency in current.depends_on:
            if isinstance(dependency, SqlResourceRef):
                continue
            visiting_names, visited_names = visit(
                current=node_by_dependency_key[_python_node_dependency_key(dependency)],
                path=(*path, current.name),
                visiting_names=visiting_names,
                visited_names=visited_names,
            )
        visiting_names = visiting_names - {current.name}
        visited_names = visited_names | {current.name}
        return visiting_names, visited_names

    for node in nodes:
        visiting, visited = visit(
            current=node,
            path=(),
            visiting_names=visiting,
            visited_names=visited,
        )


def _validate_check_dependencies(
    *,
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    task_functions: tuple[DiscoveredTaskFunction, ...],
    asset_functions: tuple[DiscoveredAssetFunction, ...],
    check_functions: tuple[DiscoveredCheckFunction, ...],
) -> None:
    allowed_dependency_keys: frozenset[object | tuple[str, str]] = frozenset(
        ("name", node.name) for node in (*loader_functions, *task_functions, *asset_functions)
    )
    check_dependency_keys: frozenset[object | tuple[str, str]] = frozenset(
        ("name", check_function.name) for check_function in check_functions
    )
    check_function: DiscoveredCheckFunction
    for check_function in check_functions:
        dependency: object
        for dependency in check_function.depends_on:
            if isinstance(dependency, SqlResourceRef):
                raise DiscoveryConflictError(
                    f"Check '{check_function.name}' depends on SQL resource '{dependency.name}'; "
                    "checks may depend on loaders, tasks, and assets only"
                )
            dependency_key: object | tuple[str, str] = _python_node_dependency_key(dependency)
            if dependency_key in check_dependency_keys:
                raise DiscoveryConflictError(
                    f"Check '{check_function.name}' depends on another check; checks may "
                    "depend on loaders, tasks, and assets only"
                )
            if dependency_key not in allowed_dependency_keys:
                raise DiscoveryConflictError(
                    f"Check '{check_function.name}' depends on an unknown Python node; "
                    "use function references to decorated loaders, tasks, or assets"
                )


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


def _validate_unique_schema_model_names(schema_files: tuple[DiscoveredSchemaFile, ...]) -> None:
    seen_names: dict[str, str] = {}
    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        model_entry: SchemaModelEntry
        for model_entry in schema_file.model_entries:
            existing_path: str | None = seen_names.get(model_entry.name)
            if existing_path is not None:
                raise DiscoveryConflictError(
                    "Duplicate schema.yml model declaration found for "
                    f"'{model_entry.name}' in {existing_path} and {schema_file.relative_path}"
                )
            seen_names[model_entry.name] = str(schema_file.relative_path)


def _validate_unique_schema_seed_names(schema_files: tuple[DiscoveredSchemaFile, ...]) -> None:
    seen_names: dict[str, str] = {}
    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            existing_path: str | None = seen_names.get(seed_entry.name)
            if existing_path is not None:
                raise DiscoveryConflictError(
                    "Duplicate seed declaration found for "
                    f"'{seed_entry.name}' in {existing_path} and {schema_file.relative_path}"
                )
            seen_names[seed_entry.name] = str(schema_file.relative_path)


def _validate_unique_logical_relation_names(
    *,
    model_files: tuple[DiscoveredSqlModelFile, ...],
    source_files: tuple[DiscoveredSourceFile, ...],
    schema_files: tuple[DiscoveredSchemaFile, ...],
) -> None:
    seen_names: dict[str, tuple[str, str]] = {}
    model_file: DiscoveredSqlModelFile
    for model_file in model_files:
        seen_names[model_file.file_path.stem] = ("model", str(model_file.relative_path))

    source_file: DiscoveredSourceFile
    for source_file in source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            seen_names[source_entry.name] = _validated_logical_relation_entry(
                seen_names=seen_names,
                name=source_entry.name,
                kind="source",
                path=str(source_file.relative_path),
            )

    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            seen_names[seed_entry.name] = _validated_logical_relation_entry(
                seen_names=seen_names,
                name=seed_entry.name,
                kind="seed",
                path=str(schema_file.relative_path),
            )


def _validated_logical_relation_entry(
    *, seen_names: dict[str, tuple[str, str]], name: str, kind: str, path: str
) -> tuple[str, str]:
    existing_entry: tuple[str, str] | None = seen_names.get(name)
    if existing_entry is not None:
        raise DiscoveryConflictError(
            f"Logical relation name '{name}' is declared as both {existing_entry[0]} "
            f"in {existing_entry[1]} and {kind} in {path}"
        )
    return (kind, path)


def _validate_unique_project_resource_names(
    discovered_inputs: DiscoveredProjectInputs,
) -> None:
    seen_names: dict[str, tuple[str, str]] = {}

    model_file: DiscoveredSqlModelFile
    for model_file in discovered_inputs.model_files:
        seen_names[model_file.file_path.stem] = _validated_project_resource_entry(
            seen_names=seen_names,
            name=model_file.file_path.stem,
            kind="model",
            path=str(model_file.relative_path),
        )

    source_file: DiscoveredSourceFile
    managed_source_names: set[str] = set()
    for source_file in discovered_inputs.source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            if source_entry.managed:
                managed_source_names.add(source_entry.name)
            seen_names[source_entry.name] = _validated_project_resource_entry(
                seen_names=seen_names,
                name=source_entry.name,
                kind="source",
                path=str(source_file.relative_path),
            )

    schema_file: DiscoveredSchemaFile
    for schema_file in discovered_inputs.schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            seen_names[seed_entry.name] = _validated_project_resource_entry(
                seen_names=seen_names,
                name=seed_entry.name,
                kind="seed",
                path=str(schema_file.relative_path),
            )

    sql_function_file: DiscoveredSqlFunctionFile
    for sql_function_file in discovered_inputs.sql_function_files:
        seen_names[sql_function_file.file_path.stem] = _validated_project_resource_entry(
            seen_names=seen_names,
            name=sql_function_file.file_path.stem,
            kind="function",
            path=str(sql_function_file.relative_path),
        )

    python_function_file: DiscoveredPythonFunctionFile
    for python_function_file in discovered_inputs.python_function_files:
        seen_names[python_function_file.file_path.stem] = _validated_project_resource_entry(
            seen_names=seen_names,
            name=python_function_file.file_path.stem,
            kind="function",
            path=str(python_function_file.relative_path),
        )

    node: (
        DiscoveredLoaderFunction
        | DiscoveredTaskFunction
        | DiscoveredAssetFunction
        | DiscoveredCheckFunction
    )
    for node in (
        *discovered_inputs.loader_functions,
        *discovered_inputs.task_functions,
        *discovered_inputs.asset_functions,
        *discovered_inputs.check_functions,
    ):
        if isinstance(node, DiscoveredLoaderFunction) and node.name in managed_source_names:
            continue
        seen_names[node.name] = _validated_project_resource_entry(
            seen_names=seen_names,
            name=node.name,
            kind=node.__class__.__name__.removeprefix("Discovered")
            .removesuffix("Function")
            .lower(),
            path=str(node.relative_path),
        )

    provider: DiscoveredProvider
    for provider in discovered_inputs.providers:
        seen_names[provider.name] = _validated_project_resource_entry(
            seen_names=seen_names,
            name=provider.name,
            kind="provider",
            path=str(provider.relative_path),
        )

    sql_hook_file: DiscoveredSqlHookFile
    for sql_hook_file in discovered_inputs.sql_hook_files:
        seen_names[sql_hook_file.name] = _validated_project_resource_entry(
            seen_names=seen_names,
            name=sql_hook_file.name,
            kind="sql hook",
            path=str(sql_hook_file.relative_path),
        )

    hook_function: DiscoveredHookFunction
    for hook_function in discovered_inputs.hook_functions:
        seen_names[hook_function.name] = _validated_project_resource_entry(
            seen_names=seen_names,
            name=hook_function.name,
            kind="python hook",
            path=str(hook_function.relative_path),
        )


def _validated_project_resource_entry(
    *, seen_names: dict[str, tuple[str, str]], name: str, kind: str, path: str
) -> tuple[str, str]:
    existing_entry: tuple[str, str] | None = seen_names.get(name)
    if existing_entry is not None:
        raise DiscoveryConflictError(
            f"Project resource name '{name}' is declared as both {existing_entry[0]} "
            f"in {existing_entry[1]} and {kind} in {path}; model, source, seed, function, "
            "loader, task, asset, check, provider, and hook names must be globally unique"
        )
    return (kind, path)


def _validate_declared_seed_files(
    *,
    schema_files: tuple[DiscoveredSchemaFile, ...],
    seed_files: tuple[DiscoveredSeedFile, ...],
) -> None:
    _validate_unique_seed_csv_names(seed_files)
    declared_seed_entries: list[tuple[SchemaSeedEntry, str]] = []
    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            declared_seed_entries.append((seed_entry, str(schema_file.relative_path)))

    seed_entry_and_path: tuple[SchemaSeedEntry, str]
    for seed_entry_and_path in declared_seed_entries:
        seed_entry: SchemaSeedEntry = seed_entry_and_path[0]
        declaration_path: str = seed_entry_and_path[1]
        matching_seed_files: tuple[DiscoveredSeedFile, ...] = tuple(
            seed_file for seed_file in seed_files if seed_file.file_path.stem == seed_entry.name
        )
        if not matching_seed_files:
            raise SeedDiscoveryError(
                "Seed declaration "
                f"'{seed_entry.name}' in {declaration_path} has no matching CSV file under seeds/"
            )
        if len(matching_seed_files) > 1:
            matching_paths: str = ", ".join(
                str(seed_file.relative_path) for seed_file in matching_seed_files
            )
            raise SeedDiscoveryError(
                f"Seed declaration '{seed_entry.name}' matches multiple CSV files: {matching_paths}"
            )

        _validate_seed_csv_header(seed_entry=seed_entry, seed_file=matching_seed_files[0])

    declared_names: set[str] = {seed_entry.name for seed_entry, _ in declared_seed_entries}
    seed_file: DiscoveredSeedFile
    for seed_file in seed_files:
        if seed_file.file_path.stem not in declared_names:
            raise SeedDiscoveryError(
                f"Seed CSV {seed_file.relative_path} has no matching declaration for seed "
                f"'{seed_file.file_path.stem}' under seeds/**/*.yml"
            )


def _validate_unique_seed_csv_names(seed_files: tuple[DiscoveredSeedFile, ...]) -> None:
    seen_paths: dict[str, Path] = {}
    seed_file: DiscoveredSeedFile
    for seed_file in seed_files:
        seed_name: str = seed_file.file_path.stem
        existing_path: Path | None = seen_paths.get(seed_name)
        if existing_path is not None:
            raise SeedDiscoveryError(
                f"Duplicate seed CSV name '{seed_name}' found: {existing_path}, "
                f"{seed_file.relative_path}. Seed CSV filenames must be unique under seeds/."
            )
        seen_paths[seed_name] = seed_file.relative_path


def _validate_seed_csv_header(
    *, seed_entry: SchemaSeedEntry, seed_file: DiscoveredSeedFile
) -> None:
    header_columns: tuple[str, ...] = _load_seed_csv_header(
        file_path=seed_file.file_path,
        delimiter=seed_entry.csv_settings.delimiter,
        quotechar=seed_entry.csv_settings.quotechar,
        escapechar=seed_entry.csv_settings.escapechar,
        doublequote=seed_entry.csv_settings.doublequote,
        skipinitialspace=seed_entry.csv_settings.skipinitialspace,
    )
    if not header_columns:
        raise SeedDiscoveryError(f"{seed_file.relative_path} must contain a CSV header row")

    seen_columns: set[str] = set()
    column_name: str
    for column_name in header_columns:
        if column_name in seen_columns:
            raise SeedDiscoveryError(
                f"{seed_file.relative_path} contains duplicate CSV header column '{column_name}'"
            )
        seen_columns.add(column_name)

    declared_columns: tuple[str, ...] = tuple(column.name for column in seed_entry.columns)
    if header_columns != declared_columns:
        raise SeedDiscoveryError(
            f"{seed_file.relative_path} header {header_columns} does not match "
            "declared seed columns "
            f"{declared_columns} for '{seed_entry.name}'"
        )


def _load_seed_csv_header(
    *,
    file_path: Path,
    delimiter: str | None,
    quotechar: str | None,
    escapechar: str | None,
    doublequote: bool | None,
    skipinitialspace: bool | None,
) -> tuple[str, ...]:
    reader_kwargs: dict[str, object] = {}
    if delimiter is not None:
        reader_kwargs["delimiter"] = delimiter
    if quotechar is not None:
        reader_kwargs["quotechar"] = quotechar
    if escapechar is not None:
        reader_kwargs["escapechar"] = escapechar
    if doublequote is not None:
        reader_kwargs["doublequote"] = doublequote
    if skipinitialspace is not None:
        reader_kwargs["skipinitialspace"] = skipinitialspace

    with file_path.open("r", encoding="utf-8", newline="") as handle:
        try:
            header_row: list[str] = next(
                csv.reader(
                    handle,
                    delimiter=delimiter or ",",
                    quotechar=quotechar,
                    escapechar=escapechar,
                    doublequote=True if doublequote is None else doublequote,
                    skipinitialspace=False if skipinitialspace is None else skipinitialspace,
                )
            )
        except StopIteration:
            return ()
    return tuple(header_row)


def _validate_path_defaults_match_models(
    *,
    path_defaults: dict[str, dict[str, object]],
    model_files: tuple[DiscoveredSqlModelFile, ...],
) -> None:
    if not path_defaults:
        return
    model_paths: tuple[str, ...] = tuple(
        str(model_file.relative_path).replace("\\", "/").removeprefix("models/")
        for model_file in model_files
    )
    model_folders: tuple[str, ...] = tuple(
        sorted(
            {
                str(Path(model_path).parent)
                for model_path in model_paths
                if str(Path(model_path).parent) != CURRENT_DIRECTORY_PATH
            }
        )
    )
    matched_keys: set[str] = set()
    model_path: str
    for model_path in model_paths:
        matched_keys.update(
            select_path_default(
                model_path=model_path,
                path_keys=tuple(path_defaults),
            ).matched_keys
        )
    path_key: str
    for path_key in path_defaults:
        if path_key in matched_keys:
            continue
        known_folders: str = ", ".join(model_folders[:5]) if model_folders else "<none>"
        raise DiscoveryConflictError(
            f"path_defaults['{path_key}'] does not match any model paths. Known model folders "
            f"include: {known_folders}"
        )
