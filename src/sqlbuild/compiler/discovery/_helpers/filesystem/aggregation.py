"""Aggregation of all filesystem discovery results into project inputs."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from sqlbuild.compiler.discovery._helpers.filesystem.command_output_sinks import (
    discover_command_output_sink_functions,
)
from sqlbuild.compiler.discovery._helpers.filesystem.core import (
    discover_adapter_file,
    discover_audit_files,
    discover_constant_files,
    discover_enum_files,
    discover_event_exporter_functions,
    discover_hook_functions,
    discover_macro_files,
    discover_materialization_files,
    discover_model_schema_files,
    discover_provider_classes,
    discover_python_function_files,
    discover_python_node_functions,
    discover_seed_files,
    discover_sql_function_files,
    discover_sql_hook_files,
)
from sqlbuild.compiler.discovery._helpers.integrations.loaders import (
    build_integration_loader_functions,
)
from sqlbuild.compiler.discovery._helpers.native.declaration_files import (
    retained_discovery_session,
)
from sqlbuild.compiler.discovery._helpers.native.model_files import (
    discover_native_model_files,
)
from sqlbuild.compiler.discovery._helpers.native.payloads import native_text_runtime
from sqlbuild.compiler.discovery._helpers.native.sql_test_files import (
    discover_native_scenario_files,
    discover_native_test_files,
)
from sqlbuild.compiler.discovery._helpers.native.yaml_files import (
    discover_native_schema_files,
    discover_native_source_files,
)
from sqlbuild.compiler.discovery._helpers.yml.project import load_local_config, load_project_config
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.models import (
    DiscoveredAssetFunction,
    DiscoveredAuditFactory,
    DiscoveredCheckFunction,
    DiscoveredCommandOutputSink,
    DiscoveredConstantFile,
    DiscoveredDeclarationFiles,
    DiscoveredEnumFile,
    DiscoveredEventExporter,
    DiscoveredHookFunction,
    DiscoveredLoaderFunction,
    DiscoveredMacroFile,
    DiscoveredMaterializationFile,
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
from sqlbuild.compiler.discovery.types import DeclarationFilesReuse
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def build_discovered_project_inputs(
    *,
    project_dir: Path,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    sql_analysis_enabled: bool,
    extract_output_column_locations: bool = True,
    declaration_reuse: DeclarationFilesReuse | None = None,
) -> DiscoveredProjectInputs:
    """Discover all project files and functions into one inputs bundle."""

    with OperationLifecycle(
        operation_kind="project", operation_name="discovery_declaration_parse"
    ) as declaration_lifecycle:
        discover_models: Callable[[], tuple[DiscoveredSqlModelFile, ...]] = partial(
            _discover_model_files,
            project_dir=project_dir,
            sql_analysis_enabled=sql_analysis_enabled,
            extract_output_column_locations=extract_output_column_locations,
        )
        discover: Callable[[], DiscoveredDeclarationFiles] = partial(
            _discover_declaration_files,
            project_dir=project_dir,
            discover_models=discover_models,
        )
        declarations: DiscoveredDeclarationFiles = (
            discover()
            if declaration_reuse is None
            else declaration_reuse.declaration_files(
                variant=f"{int(sql_analysis_enabled)}{int(extract_output_column_locations)}",
                discover=discover,
                discover_models=discover_models,
            )
        )
        declaration_lifecycle.completed(
            metadata={
                "item_count": sum(
                    len(files)
                    for files in (
                        declarations.source_files,
                        declarations.model_files,
                        declarations.enum_files,
                        declarations.constant_files,
                        declarations.model_schema_files,
                        declarations.sql_function_files,
                        declarations.sql_hook_files,
                        declarations.python_function_files,
                        declarations.schema_files,
                        declarations.seed_files,
                        declarations.test_files,
                        declarations.scenario_files,
                        declarations.audit_files,
                        declarations.macro_files,
                    )
                )
                + int(declarations.adapter_file is not None)
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
        command_output_sinks: tuple[DiscoveredCommandOutputSink, ...] = (
            discover_command_output_sink_functions(
                project_dir=project_dir,
                providers=providers,
            )
        )
        python_paths: set[Path] = {provider.relative_path for provider in providers}
        python_paths.update(node.relative_path for node in python_nodes.loaders)
        python_paths.update(node.relative_path for node in python_nodes.tasks)
        python_paths.update(node.relative_path for node in python_nodes.assets)
        python_paths.update(node.relative_path for node in python_nodes.checks)
        python_paths.update(factory.relative_path for factory in python_nodes.audit_factories)
        python_paths.update(file.relative_path for file in materialization_files)
        python_paths.update(function.relative_path for function in hook_functions)
        python_paths.update(exporter.relative_path for exporter in event_exporters)
        python_paths.update(sink.relative_path for sink in command_output_sinks)
        python_lifecycle.completed(metadata={"item_count": len(python_paths)})
    loader_functions: tuple[DiscoveredLoaderFunction, ...] = tuple(
        python_nodes.loaders
    ) + build_integration_loader_functions(declarations.source_files)
    task_functions: tuple[DiscoveredTaskFunction, ...] = tuple(python_nodes.tasks)
    asset_functions: tuple[DiscoveredAssetFunction, ...] = tuple(python_nodes.assets)
    check_functions: tuple[DiscoveredCheckFunction, ...] = tuple(python_nodes.checks)
    audit_factories: tuple[DiscoveredAuditFactory, ...] = tuple(python_nodes.audit_factories)
    return DiscoveredProjectInputs(
        project_config=project_config,
        local_config=local_config,
        project_dir=project_dir,
        model_files=declarations.model_files,
        enum_files=declarations.enum_files,
        constant_files=declarations.constant_files,
        model_schema_files=declarations.model_schema_files,
        sql_function_files=declarations.sql_function_files,
        sql_hook_files=declarations.sql_hook_files,
        python_function_files=declarations.python_function_files,
        schema_files=declarations.schema_files,
        source_files=declarations.source_files,
        seed_files=declarations.seed_files,
        test_files=declarations.test_files,
        scenario_files=declarations.scenario_files,
        audit_files=declarations.audit_files,
        macro_files=declarations.macro_files,
        materialization_files=materialization_files,
        loader_functions=loader_functions,
        task_functions=task_functions,
        asset_functions=asset_functions,
        check_functions=check_functions,
        audit_factories=audit_factories,
        hook_functions=hook_functions,
        event_exporters=event_exporters,
        command_output_sinks=command_output_sinks,
        providers=providers,
        adapter_file=declarations.adapter_file,
        native_session=declarations.native_session,
    )


def _discover_declaration_files(
    *,
    project_dir: Path,
    discover_models: Callable[[], tuple[DiscoveredSqlModelFile, ...]],
) -> DiscoveredDeclarationFiles:
    with DirectorySnapshot.scope(project_dir=project_dir):
        source_files: tuple[DiscoveredSourceFile, ...] = discover_native_source_files(
            project_dir=project_dir
        )
        model_files: tuple[DiscoveredSqlModelFile, ...] = discover_models()
        return DiscoveredDeclarationFiles(
            source_files=source_files,
            model_files=model_files,
            enum_files=discover_enum_files(project_dir=project_dir),
            constant_files=discover_constant_files(project_dir=project_dir),
            model_schema_files=discover_model_schema_files(project_dir=project_dir),
            sql_function_files=discover_sql_function_files(project_dir=project_dir),
            sql_hook_files=discover_sql_hook_files(project_dir=project_dir),
            python_function_files=discover_python_function_files(project_dir=project_dir),
            schema_files=discover_native_schema_files(project_dir=project_dir),
            seed_files=discover_seed_files(project_dir=project_dir),
            test_files=discover_native_test_files(project_dir=project_dir),
            scenario_files=discover_native_scenario_files(project_dir=project_dir),
            audit_files=discover_audit_files(project_dir=project_dir),
            macro_files=discover_macro_files(project_dir=project_dir),
            adapter_file=discover_adapter_file(project_dir=project_dir),
            native_session=retained_discovery_session(project_dir=project_dir),
        )


def _discover_model_files(
    *,
    project_dir: Path,
    sql_analysis_enabled: bool,
    extract_output_column_locations: bool,
) -> tuple[DiscoveredSqlModelFile, ...]:
    return discover_native_model_files(
        project_dir=project_dir,
        extract_implicit_alias_columns=sql_analysis_enabled,
        extract_output_column_locations=extract_output_column_locations,
    )


def build_tolerant_scope_discovery(*, project_dir: Path) -> TolerantScopeDiscovery:
    """Aggregate bounded scope inputs while retaining independent authored faults."""

    with DirectorySnapshot.scope(project_dir=project_dir):
        return _build_tolerant_scope_discovery(project_dir=project_dir)


def _build_tolerant_scope_discovery(*, project_dir: Path) -> TolerantScopeDiscovery:
    _ = native_text_runtime()
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
        function=discover_native_source_files, project_dir=project_dir
    )
    audits, audit_faults = _discover_category(
        function=discover_audit_files, project_dir=project_dir
    )
    model_schemas, model_schema_faults = _discover_category(
        function=discover_model_schema_files, project_dir=project_dir
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
        model_schema_files=model_schemas,
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
        declaration_faults=(*declaration_faults, *model_schema_faults),
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
    models: tuple[DiscoveredSqlModelFile, ...] = discover_native_model_files(
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
    tests: tuple[DiscoveredSqlTestFile, ...] = discover_native_test_files(
        project_dir=project_dir, on_fault=faults.append
    )
    scenarios: tuple[DiscoveredSqlScenarioFile, ...] = discover_native_scenario_files(
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
