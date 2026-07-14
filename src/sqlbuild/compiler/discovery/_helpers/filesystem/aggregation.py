"""Aggregation of all filesystem discovery results into project inputs."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_adapter_file,
    discover_audit_files,
    discover_hook_functions,
    discover_macro_files,
    discover_materialization_files,
    discover_model_files,
    discover_provider_classes,
    discover_python_function_files,
    discover_python_node_functions,
    discover_scenario_files,
    discover_schema_files,
    discover_seed_files,
    discover_source_files,
    discover_sql_function_files,
    discover_test_files,
)
from sqlbuild.compiler.discovery._helpers.integrations.loaders import (
    build_integration_loader_functions,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredAssetFunction,
    DiscoveredCheckFunction,
    DiscoveredLoaderFunction,
    DiscoveredProjectInputs,
    DiscoveredProvider,
    DiscoveredPythonNodeFunctions,
    DiscoveredSourceFile,
    DiscoveredTaskFunction,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def build_discovered_project_inputs(
    *,
    project_dir: Path,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    sql_analysis_enabled: bool,
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
        model_files=discover_model_files(
            project_dir=project_dir,
            extract_implicit_alias_columns=sql_analysis_enabled,
        ),
        sql_function_files=discover_sql_function_files(project_dir=project_dir),
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
