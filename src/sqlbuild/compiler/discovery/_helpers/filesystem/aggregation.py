"""Aggregation of all filesystem discovery results into project inputs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlbuild._native import (
    discover_audit_files,
    discover_constant_files,
    discover_enum_files,
    discover_macro_files,
    discover_model_files,
    discover_model_schema_files,
    discover_scenario_files,
    discover_source_files,
    discover_sql_function_files,
    discover_sql_hook_files,
    discover_test_files,
)
from sqlbuild.compiler.discovery._helpers.yml.project import load_local_config, load_project_config
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.models import (
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredMacroFile,
    DiscoveredProjectInputs,
    DiscoveredSqlModelFile,
    DiscoveredSqlScenarioFile,
    DiscoveredSqlTestFile,
    DiscoveryFileFault,
    TolerantScopeDiscovery,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def build_tolerant_scope_discovery(*, project_dir: Path) -> TolerantScopeDiscovery:
    """Aggregate bounded scope inputs while retaining independent authored faults."""

    with DirectorySnapshot.scope(project_dir=project_dir):
        return _build_tolerant_scope_discovery(project_dir=project_dir)


def _build_tolerant_scope_discovery(*, project_dir: Path) -> TolerantScopeDiscovery:
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
