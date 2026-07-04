"""Discovery entrypoints."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.helpers.filesystem.core import (
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
from sqlbuild.compiler.discovery.helpers.integrations.loaders import (
    build_integration_loader_functions,
)
from sqlbuild.compiler.discovery.helpers.validation.discovery import validate_discovered_inputs
from sqlbuild.compiler.discovery.helpers.yml.project import (
    load_local_config,
    load_project_config,
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
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig


def discover_project_inputs(
    *, project_dir: Path, sql_analysis_enabled_override: bool | None = None
) -> DiscoveredProjectInputs:
    """Load all raw project inputs from disk before semantic resolution."""

    project_config: ProjectConfig = load_project_config(project_dir=project_dir)
    local_config: LocalConfig = load_local_config(project_dir=project_dir)
    sql_analysis_enabled: bool = (
        sql_analysis_enabled_override
        if sql_analysis_enabled_override is not None
        else (
            local_config.settings.sql_analysis
            if "sql_analysis" in local_config.setting_overrides
            else project_config.settings.sql_analysis
        )
    )

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
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=project_config,
        local_config=local_config,
        model_files=discover_model_files(
            project_dir=project_dir,
            extract_implicit_alias_columns=_extract_implicit_alias_columns(
                sql_analysis_enabled=sql_analysis_enabled
            ),
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
    validate_discovered_inputs(discovered_inputs)
    return discovered_inputs


def _extract_implicit_alias_columns(*, sql_analysis_enabled: bool) -> bool:
    """Guessed alias locations only feed analysis diagnostics, so follow sql_analysis."""

    return sql_analysis_enabled
