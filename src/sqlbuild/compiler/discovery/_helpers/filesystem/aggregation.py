"""Aggregation of all filesystem discovery results into project inputs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_adapter_file,
    discover_audit_files,
    discover_constant_files,
    discover_enum_files,
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
    DiscoveredAssetFunction,
    DiscoveredCheckFunction,
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredLoaderFunction,
    DiscoveredMacroFile,
    DiscoveredProjectInputs,
    DiscoveredProvider,
    DiscoveredPythonNodeFunctions,
    DiscoveredSourceFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestFile,
    DiscoveredTaskFunction,
    DiscoveryFileFault,
    TolerantScopeDiscovery,
)
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

    source_files: tuple[DiscoveredSourceFile, ...] = discover_source_files(project_dir=project_dir)
    providers: tuple[DiscoveredProvider, ...] = discover_provider_classes(project_dir=project_dir)
    python_nodes: DiscoveredPythonNodeFunctions = discover_python_node_functions(
        project_dir=project_dir,
        providers=providers,
    )
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
        model_files=discover_model_files(
            project_dir=project_dir,
            extract_implicit_alias_columns=sql_analysis_enabled,
            extract_output_column_locations=extract_output_column_locations,
        ),
        enum_files=discover_enum_files(project_dir=project_dir),
        constant_files=discover_constant_files(project_dir=project_dir),
        model_schema_files=discover_model_schema_files(project_dir=project_dir),
        sql_function_files=discover_sql_function_files(project_dir=project_dir),
        sql_hook_files=discover_sql_hook_files(project_dir=project_dir),
        python_function_files=discover_python_function_files(project_dir=project_dir),
        schema_files=discover_schema_files(project_dir=project_dir),
        source_files=source_files,
        seed_files=discover_seed_files(project_dir=project_dir),
        test_files=discover_test_files(project_dir=project_dir),
        scenario_files=discover_scenario_files(project_dir=project_dir),
        audit_files=discover_audit_files(project_dir=project_dir),
        macro_files=discover_macro_files(project_dir=project_dir),
        materialization_files=discover_materialization_files(
            project_dir=project_dir,
            providers=providers,
        ),
        loader_functions=loader_functions,
        task_functions=task_functions,
        asset_functions=asset_functions,
        check_functions=check_functions,
        hook_functions=discover_hook_functions(project_dir=project_dir, providers=providers),
        providers=providers,
        adapter_file=discover_adapter_file(project_dir=project_dir),
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
    try:
        enums: tuple[DiscoveredEnumFile, ...] = discover_enum_files(
            project_dir=project_dir, on_fault=faults.append
        )
        constants: tuple[DiscoveredConstantFile, ...] = discover_constant_files(
            project_dir=project_dir, on_fault=faults.append
        )
        macros: tuple[DiscoveredMacroFile, ...] = discover_macro_files(project_dir=project_dir)
    except (OSError, UnicodeError, ValueError, SyntaxError) as error:
        faults.append(
            DiscoveryFileFault(
                path=None,
                message=str(error).replace(str(project_dir), "."),
            )
        )
        enums, constants, macros = (), (), ()
    return enums, constants, macros, tuple(faults)


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
