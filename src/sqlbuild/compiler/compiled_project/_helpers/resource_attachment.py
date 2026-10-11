"""Seeds, functions and sources attached natively and held by the compile's native project."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.types import FunctionInput, SeedInput, SourceInput
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSourceFile,
)
from sqlbuild.compiler.scopes.types import ResourceKind
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    SchemaSeedEntry,
    SettingsConfig,
    SourceEntry,
    TargetConfig,
)


def attach_seeds_impl(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: _native.NativeCompiledProject,
) -> tuple[SeedInput, ...]:
    """Pair every declared seed with its CSV file; raise for a declaration without one."""

    declarations: list[tuple[SchemaSeedEntry, DiscoveredSchemaFile]] = []
    for schema_file in discovered_inputs.schema_files:
        declarations.extend((seed_entry, schema_file) for seed_entry in schema_file.seed_entries)
    return tuple(
        native_project.attach_seeds(
            declarations, list(discovered_inputs.seed_files), CompileInputError
        )
    )


def attach_functions_impl(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: _native.NativeCompiledProject,
    settings: tuple[SettingsConfig, TargetConfig | None, str],
    no_sql_validation: bool,
    python_functions_inherit_default_namespace: bool,
) -> tuple[FunctionInput, ...]:
    """Attach and validate every SQL, then Python, function in discovery order."""

    effective_settings, target_config, adapter_name = settings
    defaults: DefaultsConfig = discovered_inputs.project_config.defaults
    sql_rows: list[tuple[object, ...]] = [
        (
            str(function_file.file_path),
            str(function_file.relative_path),
            function_file.file_path.stem,
            function_file,
            function_file.header_values,
            function_file.body_sql,
            function_file.contents,
        )
        for function_file in discovered_inputs.sql_function_files
    ]
    python_rows: list[tuple[object, ...]] = [
        (
            str(function_file.file_path),
            str(function_file.relative_path),
            function_file.file_path.stem,
            function_file,
            function_file.header_values,
            function_file.body_python,
            None,
        )
        for function_file in discovered_inputs.python_function_files
    ]
    return tuple(
        native_project.attach_functions(
            (sql_rows, python_rows),
            (
                adapter_name,
                effective_settings.sql_analysis and not no_sql_validation,
                (
                    defaults.function_database
                    if defaults.function_database is not None
                    else defaults.database,
                    defaults.function_schema
                    if defaults.function_schema is not None
                    else defaults.schema,
                ),
                None if target_config is None else (target_config.database, target_config.schema),
                python_functions_inherit_default_namespace,
                ResourceKind.FUNCTION,
            ),
        )
    )


def attach_sources_impl(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    native_project: _native.NativeCompiledProject,
    effective_settings: SettingsConfig,
    no_sql_validation: bool,
) -> tuple[SourceInput, ...]:
    """Expand and validate every discovered source in declaration order."""

    rows: list[tuple[str, DiscoveredSourceFile, SourceEntry]] = []
    for source_file in discovered_inputs.source_files:
        rows.extend(
            (str(source_file.file_path), source_file, entry) for entry in source_file.source_entries
        )
    return tuple(
        native_project.attach_sources(
            rows,
            (
                discovered_inputs.project_config.defaults.contract,
                effective_settings.sql_analysis and not no_sql_validation,
                ResourceKind.SOURCE,
            ),
        )
    )
