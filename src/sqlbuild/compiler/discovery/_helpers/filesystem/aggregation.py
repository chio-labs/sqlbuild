"""Aggregation of all filesystem discovery results into project inputs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_adapter_file,
    discover_audit_files,
    discover_constant_files,
    discover_enum_files,
    discover_event_exporter_functions,
    discover_hook_functions,
    discover_macro_files,
    discover_materialization_files,
    discover_model_files,
    discover_model_schema_files,
    discover_provider_classes,
    discover_python_function_files,
    discover_python_node_functions,
    discover_scenario_files,
    discover_schema_files,
    discover_seed_files,
    discover_source_files,
    discover_sql_function_files,
    discover_sql_hook_files,
    discover_test_files,
)
from sqlbuild.compiler.discovery._helpers.integrations.loaders import (
    build_integration_loader_functions,
)
from sqlbuild.compiler.discovery._helpers.yml.project import load_local_config, load_project_config
from sqlbuild.compiler.discovery.models import (
    DiscoveredAdapterFile,
    DiscoveredAssetFunction,
    DiscoveredAuditFile,
    DiscoveredCheckFunction,
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredEventExporter,
    DiscoveredHookFunction,
    DiscoveredLoaderFunction,
    DiscoveredMacroFile,
    DiscoveredMaterializationFile,
    DiscoveredModelSchemaFile,
    DiscoveredProjectInputs,
    DiscoveredProvider,
    DiscoveredPythonFunctionFile,
    DiscoveredPythonNodeFunctions,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlHookFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestFile,
    DiscoveredTaskFunction,
    DiscoveryFileFault,
    TolerantScopeDiscovery,
)
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def build_discovered_project_inputs(
    *,
    project_dir: Path,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    sql_analysis_enabled: bool,
    extract_output_column_locations: bool = True,
) -> DiscoveredProjectInputs:
    """Discover all project files and functions into one inputs bundle."""

    with OperationLifecycle(
        operation_kind="project", operation_name="discovery_declaration_parse"
    ) as declaration_lifecycle:
        source_files: tuple[DiscoveredSourceFile, ...] = discover_source_files(
            project_dir=project_dir
        )
        model_files: tuple[DiscoveredSqlModelFile, ...] = discover_model_files(
            project_dir=project_dir,
            extract_implicit_alias_columns=sql_analysis_enabled,
            extract_output_column_locations=extract_output_column_locations,
        )
        enum_files: tuple[DiscoveredEnumFile, ...] = discover_enum_files(project_dir=project_dir)
        constant_files: tuple[DiscoveredConstantFile, ...] = discover_constant_files(
            project_dir=project_dir
        )
        model_schema_files: tuple[DiscoveredModelSchemaFile, ...] = discover_model_schema_files(
            project_dir=project_dir
        )
        sql_function_files: tuple[DiscoveredSqlFunctionFile, ...] = discover_sql_function_files(
            project_dir=project_dir
        )
        sql_hook_files: tuple[DiscoveredSqlHookFile, ...] = discover_sql_hook_files(
            project_dir=project_dir
        )
        python_function_files: tuple[DiscoveredPythonFunctionFile, ...] = (
            discover_python_function_files(project_dir=project_dir)
        )
        schema_files: tuple[DiscoveredSchemaFile, ...] = discover_schema_files(
            project_dir=project_dir
        )
        seed_files: tuple[DiscoveredSeedFile, ...] = discover_seed_files(project_dir=project_dir)
        test_files: tuple[DiscoveredSqlTestFile, ...] = discover_test_files(project_dir=project_dir)
        scenario_files: tuple[DiscoveredSqlScenarioFile, ...] = discover_scenario_files(
            project_dir=project_dir
        )
        audit_files: tuple[DiscoveredAuditFile, ...] = discover_audit_files(project_dir=project_dir)
        macro_files: tuple[DiscoveredMacroFile, ...] = discover_macro_files(project_dir=project_dir)
        adapter_file: DiscoveredAdapterFile | None = discover_adapter_file(project_dir=project_dir)
        declaration_lifecycle.completed(
            metadata={
                "item_count": sum(
                    len(files)
                    for files in (
                        source_files,
                        model_files,
                        enum_files,
                        constant_files,
                        model_schema_files,
                        sql_function_files,
                        sql_hook_files,
                        python_function_files,
                        schema_files,
                        seed_files,
                        test_files,
                        scenario_files,
                        audit_files,
                        macro_files,
                    )
                )
                + int(adapter_file is not None)
            }
        )
    with OperationLifecycle(
        operation_kind="project", operation_name="discovery_python_import"
    ) as python_lifecycle:
        providers: tuple[DiscoveredProvider, ...] = discover_provider_classes(
            project_dir=project_dir
        )
        python_nodes: DiscoveredPythonNodeFunctions = discover_python_node_functions(
            project_dir=project_dir,
            providers=providers,
        )
        materialization_files: tuple[DiscoveredMaterializationFile, ...] = (
            discover_materialization_files(
                project_dir=project_dir,
                providers=providers,
            )
        )
        hook_functions: tuple[DiscoveredHookFunction, ...] = discover_hook_functions(
            project_dir=project_dir,
            providers=providers,
        )
        event_exporters: tuple[DiscoveredEventExporter, ...] = discover_event_exporter_functions(
            project_dir=project_dir, providers=providers
        )
        python_paths: set[Path] = {provider.relative_path for provider in providers}
        python_paths.update(node.relative_path for node in python_nodes.loaders)
        python_paths.update(node.relative_path for node in python_nodes.tasks)
        python_paths.update(node.relative_path for node in python_nodes.assets)
        python_paths.update(node.relative_path for node in python_nodes.checks)
        python_paths.update(file.relative_path for file in materialization_files)
        python_paths.update(function.relative_path for function in hook_functions)
        python_paths.update(exporter.relative_path for exporter in event_exporters)
        python_lifecycle.completed(metadata={"item_count": len(python_paths)})
    loader_functions: tuple[DiscoveredLoaderFunction, ...] = tuple(
        python_nodes.loaders
    ) + build_integration_loader_functions(source_files)
    task_functions: tuple[DiscoveredTaskFunction, ...] = tuple(python_nodes.tasks)
    asset_functions: tuple[DiscoveredAssetFunction, ...] = tuple(python_nodes.assets)
    check_functions: tuple[DiscoveredCheckFunction, ...] = tuple(python_nodes.checks)
    return DiscoveredProjectInputs(
        project_config=project_config,
        local_config=local_config,
        project_dir=project_dir,
        model_files=model_files,
        enum_files=enum_files,
        constant_files=constant_files,
        model_schema_files=model_schema_files,
        sql_function_files=sql_function_files,
        sql_hook_files=sql_hook_files,
        python_function_files=python_function_files,
        schema_files=schema_files,
        source_files=source_files,
        seed_files=seed_files,
        test_files=test_files,
        scenario_files=scenario_files,
        audit_files=audit_files,
        macro_files=macro_files,
        materialization_files=materialization_files,
        loader_functions=loader_functions,
        task_functions=task_functions,
        asset_functions=asset_functions,
        check_functions=check_functions,
        hook_functions=hook_functions,
        event_exporters=event_exporters,
        providers=providers,
        adapter_file=adapter_file,
    )


def build_tolerant_scope_discovery(*, project_dir: Path) -> TolerantScopeDiscovery:
    """Aggregate bounded scope inputs while retaining independent authored faults."""

    project_config, local_config, config_faults = _discover_configs(project_dir=project_dir)
    models, model_faults = _discover_models(project_dir=project_dir)
    enums, constants, macros, declaration_faults = _discover_declarations(project_dir=project_dir)
    tests, scenarios, relationship_faults = _discover_relationships(project_dir=project_dir)
    sql_functions, function_faults = _discover_category(
        function=discover_sql_function_files, project_dir=project_dir
    )
    sql_hooks, hook_faults = _discover_category(
        function=discover_sql_hook_files, project_dir=project_dir
    )
    sources, source_faults = _discover_category(
        function=discover_source_files, project_dir=project_dir
    )
    audits, audit_faults = _discover_category(
        function=discover_audit_files, project_dir=project_dir
    )
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=project_config,
        local_config=local_config,
        project_dir=project_dir,
        model_files=models,
        enum_files=enums,
        constant_files=constants,
        sql_function_files=sql_functions,
        sql_hook_files=sql_hooks,
        source_files=sources,
        test_files=tests,
        scenario_files=scenarios,
        audit_files=audits,
        macro_files=macros,
    )
    return TolerantScopeDiscovery(
        discovered_inputs=discovered_inputs,
        resource_faults=(
            *model_faults,
            *function_faults,
            *hook_faults,
            *source_faults,
            *audit_faults,
        ),
        declaration_faults=declaration_faults,
        relationship_faults=relationship_faults,
        config_faults=config_faults,
    )


def _discover_configs(
    *, project_dir: Path
) -> tuple[ProjectConfig, LocalConfig, tuple[DiscoveryFileFault, ...]]:
    faults: list[DiscoveryFileFault] = []
    try:
        project_config: ProjectConfig = load_project_config(project_dir=project_dir)
    except (OSError, UnicodeError, ValueError, SyntaxError) as error:
        project_config = ProjectConfig(name=project_dir.name or "project", adapter="duckdb")
        faults.append(
            DiscoveryFileFault(
                path=Path("sqlbuild_project.toml"),
                message=str(error).replace(str(project_dir), "."),
            )
        )
    try:
        local_config: LocalConfig = load_local_config(project_dir=project_dir)
    except (OSError, UnicodeError, ValueError, SyntaxError) as error:
        local_config = LocalConfig()
        faults.append(
            DiscoveryFileFault(
                path=Path("sqlbuild_local.toml"),
                message=str(error).replace(str(project_dir), "."),
            )
        )
    return project_config, local_config, tuple(faults)


def _discover_models(
    *, project_dir: Path
) -> tuple[tuple[DiscoveredSqlModelFile, ...], tuple[DiscoveryFileFault, ...]]:
    faults: list[DiscoveryFileFault] = []
    models: tuple[DiscoveredSqlModelFile, ...] = discover_model_files(
        project_dir=project_dir,
        extract_implicit_alias_columns=False,
        extract_output_column_locations=False,
        on_fault=faults.append,
    )
    return models, tuple(faults)


def _discover_declarations(
    *, project_dir: Path
) -> tuple[
    tuple[DiscoveredEnumFile, ...],
    tuple[DiscoveredConstantFile, ...],
    tuple[DiscoveredMacroFile, ...],
    tuple[DiscoveryFileFault, ...],
]:
    faults: list[DiscoveryFileFault] = []
    enums: tuple[DiscoveredEnumFile, ...] = ()
    constants: tuple[DiscoveredConstantFile, ...] = ()
    macros: tuple[DiscoveredMacroFile, ...] = ()
    try:
        enums = discover_enum_files(
            project_dir=project_dir,
            on_fault=faults.append,
            isolate_declaration_kind=True,
        )
    except (OSError, UnicodeError, ValueError, SyntaxError) as error:
        faults.append(_category_fault(project_dir=project_dir, error=error))
    try:
        constants = discover_constant_files(
            project_dir=project_dir,
            on_fault=faults.append,
            isolate_declaration_kind=True,
        )
    except (OSError, UnicodeError, ValueError, SyntaxError) as error:
        faults.append(_category_fault(project_dir=project_dir, error=error))
    try:
        macros = discover_macro_files(
            project_dir=project_dir,
            isolate_declaration_kind=True,
        )
    except (OSError, UnicodeError, ValueError, SyntaxError) as error:
        faults.append(_category_fault(project_dir=project_dir, error=error))
    return enums, constants, macros, tuple(faults)


def _category_fault(*, project_dir: Path, error: Exception) -> DiscoveryFileFault:
    return DiscoveryFileFault(
        path=None,
        message=str(error).replace(str(project_dir), "."),
    )


def _discover_relationships(
    *, project_dir: Path
) -> tuple[
    tuple[DiscoveredSqlTestFile, ...],
    tuple[DiscoveredSqlScenarioFile, ...],
    tuple[DiscoveryFileFault, ...],
]:
    faults: list[DiscoveryFileFault] = []
    tests: tuple[DiscoveredSqlTestFile, ...] = discover_test_files(
        project_dir=project_dir, on_fault=faults.append
    )
    scenarios: tuple[DiscoveredSqlScenarioFile, ...] = discover_scenario_files(
        project_dir=project_dir, on_fault=faults.append
    )
    return tests, scenarios, tuple(faults)


def _discover_category[Record](
    *, function: Callable[..., tuple[Record, ...]], project_dir: Path
) -> tuple[tuple[Record, ...], tuple[DiscoveryFileFault, ...]]:
    faults: list[DiscoveryFileFault] = []
    try:
        records: tuple[Record, ...] = function(
            project_dir=project_dir,
            on_fault=faults.append,
        )
        return records, tuple(faults)
    except (OSError, UnicodeError, ValueError, SyntaxError) as error:
        faults.append(
            DiscoveryFileFault(
                path=None,
                message=str(error).replace(str(project_dir), "."),
            )
        )
        return (), tuple(faults)
