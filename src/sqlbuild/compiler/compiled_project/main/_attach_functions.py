"""Functions attached natively by the compile's model loop and held by its native project."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.types import FunctionInput
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
)
from sqlbuild.compiler.scopes.types import ResourceKind
from sqlbuild.spec.contracts.models import DefaultsConfig, SettingsConfig, TargetConfig


def attach_functions(
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
