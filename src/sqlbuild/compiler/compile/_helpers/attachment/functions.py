"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from sqlbuild.compiler.compile._helpers.analysis.columns import infer_columns_with_sql_analysis
from sqlbuild.compiler.compile._helpers.analysis.validation import (
    validate_function_sql_syntax,
)
from sqlbuild.compiler.compile._helpers.attachment.references import (
    build_known_function_names,
    build_known_ref_names,
    build_known_seed_names,
    build_known_source_names,
    build_known_table_function_names,
    validate_function_references,
)
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import reject_cursor_intrinsics
from sqlbuild.compiler.compile._helpers.render.declarations import resolve_declaration_expansion
from sqlbuild.compiler.compile._helpers.render.sql_vars import (
    expand_authored_sql,
)
from sqlbuild.compiler.compile._helpers.render.templating import (
    expand_template_data,
)
from sqlbuild.compiler.compile.constants import (
    PRESERVE_TARGET_VALUE,
    TABLE_FUNCTION_RETURN_KEYS,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompileSqlFunctionInput,
    CompileSqlReference,
    DeclarationExpansionContext,
    FunctionArgument,
    FunctionReturnColumn,
    InferredColumn,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.compile.types import (
    FunctionLanguage,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredPythonFunctionFile,
    DiscoveredSqlFunctionFile,
)
from sqlbuild.compiler.sql_analysis.main.import_polyglot import import_polyglot
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    SettingsConfig,
    TargetConfig,
)


@dataclass(frozen=True)
class _PythonFunctionBuildContext:
    """Run-constant inputs for building one Python function compile input."""

    effective_vars: dict[str, object]
    effective_settings: SettingsConfig
    adapter_name: str
    no_sql_validation: bool
    database: str | None
    schema: str | None
    python_functions_inherit_default_namespace: bool


_HOOK_TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{[^}]+\}")
_LEGACY_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hook", "post_hook"})
_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_HOOK_CONTEXT_PARAMETER_NAMES: frozenset[str] = frozenset(
    {"ctx", "context", "_ctx", "hook_context"}
)


def build_sql_function_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    effective_vars: dict[str, object],
    effective_settings: SettingsConfig,
    target_config: TargetConfig | None,
    adapter_name: str,
    macro_context: MacroContext,
    loaded_macros: dict[str, LoadedMacro],
    declaration_expansion: DeclarationExpansionContext,
    no_sql_validation: bool = False,
    python_functions_inherit_default_namespace: bool = True,
) -> tuple[CompileSqlFunctionInput, ...]:
    """Attach and validate SQL function metadata."""

    known_model_names: set[str] = build_known_ref_names(discovered_inputs)
    known_seed_names: set[str] = build_known_seed_names(discovered_inputs)
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    known_function_names: set[str] = build_known_function_names(discovered_inputs)
    known_table_function_names: set[str] = build_known_table_function_names(discovered_inputs)
    database, schema = _resolve_function_namespace(
        defaults=discovered_inputs.project_config.defaults,
        target_config=target_config,
        effective_vars=effective_vars,
    )
    known_names: set[str] = set()
    function_inputs: list[CompileSqlFunctionInput] = []
    function_file: DiscoveredSqlFunctionFile
    for function_file in discovered_inputs.sql_function_files:
        function_name: str = function_file.file_path.stem
        if function_name in known_names:
            raise CompileInputError(f"Duplicate SQL function name '{function_name}'")
        known_names.add(function_name)
        header_values: dict[str, object] = function_file.header_values
        raw_returns: object | None = header_values.get("returns")
        if raw_returns is None:
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} must declare returns"
            )
        arguments: tuple[FunctionArgument, ...] = _parse_function_arguments(
            function_file=function_file,
            effective_vars=effective_vars,
        )
        returns: str
        return_columns: tuple[FunctionReturnColumn, ...]
        returns, return_columns = _parse_sql_function_returns(
            raw_returns=raw_returns,
            function_file=function_file,
            effective_vars=effective_vars,
        )
        raw_database: object | None = header_values.get("database")
        raw_schema: object | None = header_values.get("schema")
        function_database: str | None = (
            _expand_function_header_value(
                raw_value=raw_database,
                effective_vars=effective_vars,
                context_label=f"SQL function {function_file.relative_path} database",
            )
            if isinstance(raw_database, str)
            else database
        )
        function_schema: str | None = (
            _expand_function_header_value(
                raw_value=raw_schema,
                effective_vars=effective_vars,
                context_label=f"SQL function {function_file.relative_path} schema",
            )
            if isinstance(raw_schema, str)
            else schema
        )
        scoped_declarations: DeclarationExpansionContext = resolve_declaration_expansion(
            context=declaration_expansion, file_path=function_file.file_path
        )
        expanded_body_sql: str = expand_authored_sql(
            sql=function_file.body_sql,
            file_path=function_file.file_path,
            effective_vars=effective_vars,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
            declarations=scoped_declarations.declarations,
            value_renderer=scoped_declarations.value_renderer,
            collection_rendering=scoped_declarations.collection_rendering,
        )
        reject_cursor_intrinsics(
            sql=expanded_body_sql,
            context=f"SQL function '{function_name}'",
        )
        if (
            effective_settings.sql_analysis
            and not no_sql_validation
            and effective_settings.sql_validation
        ):
            argument: FunctionArgument
            for argument in arguments:
                validate_native_type(
                    type_sql=argument.type,
                    adapter_name=adapter_name,
                    context=(
                        f"SQL function {function_file.relative_path} argument '{argument.name}'"
                    ),
                )
            if return_columns:
                return_column: FunctionReturnColumn
                for return_column in return_columns:
                    validate_native_type(
                        type_sql=return_column.type,
                        adapter_name=adapter_name,
                        context=(
                            f"SQL function {function_file.relative_path} return column "
                            f"'{return_column.name}'"
                        ),
                    )
            else:
                validate_native_type(
                    type_sql=returns,
                    adapter_name=adapter_name,
                    context=f"SQL function {function_file.relative_path} return type",
                )
            validate_function_sql_syntax(
                body_sql=expanded_body_sql,
                function_name=function_name,
                file_path=function_file.file_path,
            )
            if return_columns:
                _validate_table_function_output_contract(
                    body_sql=expanded_body_sql,
                    return_columns=return_columns,
                    function_file=function_file,
                )
        references: tuple[CompileSqlReference, ...] = extract_sql_references(expanded_body_sql)
        validate_function_references(
            references=references,
            function_file=function_file,
            known_model_names=known_model_names,
            known_seed_names=known_seed_names,
            known_source_names=known_source_names,
            known_function_names=known_function_names,
            known_table_function_names=known_table_function_names,
        )
        function_inputs.append(
            CompileSqlFunctionInput(
                function_file=function_file,
                name=function_name,
                arguments=arguments,
                returns=returns,
                body_sql=expanded_body_sql,
                return_columns=return_columns,
                references=references,
                database=function_database,
                schema=function_schema,
                fingerprint_database=function_database,
                fingerprint_schema=function_schema,
                replay_on_change=_parse_optional_function_header(
                    header_values=header_values,
                    key="replay_on_change",
                    effective_vars=effective_vars,
                    relative_path=function_file.relative_path,
                    language="SQL",
                ),
            )
        )
    python_context: _PythonFunctionBuildContext = _PythonFunctionBuildContext(
        effective_vars=effective_vars,
        effective_settings=effective_settings,
        adapter_name=adapter_name,
        no_sql_validation=no_sql_validation,
        database=database,
        schema=schema,
        python_functions_inherit_default_namespace=(python_functions_inherit_default_namespace),
    )
    python_function_file: DiscoveredPythonFunctionFile
    for python_function_file in discovered_inputs.python_function_files:
        function_name = python_function_file.file_path.stem
        if function_name in known_names:
            raise CompileInputError(f"Duplicate function name '{function_name}'")
        known_names.add(function_name)
        function_inputs.append(
            _build_python_function_input(
                python_function_file=python_function_file,
                context=python_context,
            )
        )
    return tuple(function_inputs)


def _validate_table_function_output_contract(
    *,
    body_sql: str,
    return_columns: tuple[FunctionReturnColumn, ...],
    function_file: DiscoveredSqlFunctionFile,
) -> None:
    inferred_columns: tuple[InferredColumn, ...] | None = infer_columns_with_sql_analysis(
        query_sql=body_sql
    )
    if not inferred_columns:
        return
    declared_count: int = len(return_columns)
    inferred_count: int = len(inferred_columns)
    if declared_count == inferred_count:
        return
    raise CompileInputError(
        f"SQL table function {function_file.relative_path} declares {declared_count} return "
        f"columns but its query produces {inferred_count}"
    )


def _build_python_function_input(
    *,
    python_function_file: DiscoveredPythonFunctionFile,
    context: _PythonFunctionBuildContext,
) -> CompileSqlFunctionInput:
    effective_vars: dict[str, object] = context.effective_vars
    function_name: str = python_function_file.file_path.stem
    header_values: dict[str, object] = python_function_file.header_values
    raw_returns: object | None = header_values.get("returns")
    if not isinstance(raw_returns, str) or not raw_returns.strip():
        raise CompileInputError(
            f"Python function file {python_function_file.relative_path} must declare returns"
        )
    arguments: tuple[FunctionArgument, ...] = _parse_python_function_arguments(
        function_file=python_function_file, effective_vars=effective_vars
    )
    returns: str = _expand_function_header_value(
        raw_value=raw_returns.strip(),
        effective_vars=effective_vars,
        context_label=f"Python function {python_function_file.relative_path} returns",
    )
    runtime_version: str = _parse_required_string_header(
        header_values=header_values,
        key="runtime_version",
        relative_path=python_function_file.relative_path,
        language="Python",
    )
    entry_point: str = _parse_required_string_header(
        header_values=header_values,
        key="entry_point",
        relative_path=python_function_file.relative_path,
        language="Python",
    )
    packages: tuple[str, ...] = _parse_python_packages(
        raw_packages=header_values.get("packages"),
        relative_path=python_function_file.relative_path,
    )
    raw_database: object | None = header_values.get("database")
    raw_schema: object | None = header_values.get("schema")
    inherit: bool = context.python_functions_inherit_default_namespace
    function_database: str | None
    if isinstance(raw_database, str):
        function_database = _expand_function_header_value(
            raw_value=raw_database,
            effective_vars=effective_vars,
            context_label=f"Python function {python_function_file.relative_path} database",
        )
    else:
        function_database = context.database if inherit else None
    function_schema: str | None
    if isinstance(raw_schema, str):
        function_schema = _expand_function_header_value(
            raw_value=raw_schema,
            effective_vars=effective_vars,
            context_label=f"Python function {python_function_file.relative_path} schema",
        )
    else:
        function_schema = context.schema if inherit else None
    fingerprint_database: str | None = (
        function_database if isinstance(raw_database, str) else context.database
    )
    fingerprint_schema: str | None = (
        function_schema if isinstance(raw_schema, str) else context.schema
    )
    if (
        context.effective_settings.sql_analysis
        and not context.no_sql_validation
        and context.effective_settings.sql_validation
    ):
        argument: FunctionArgument
        for argument in arguments:
            validate_native_type(
                type_sql=argument.type,
                adapter_name=context.adapter_name,
                context=(
                    f"Python function {python_function_file.relative_path} "
                    f"argument '{argument.name}'"
                ),
            )
        validate_native_type(
            type_sql=returns,
            adapter_name=context.adapter_name,
            context=f"Python function {python_function_file.relative_path} return type",
        )
    return CompileSqlFunctionInput(
        function_file=python_function_file,
        name=function_name,
        arguments=arguments,
        returns=returns,
        body_sql=python_function_file.body_python,
        database=function_database,
        schema=function_schema,
        fingerprint_database=fingerprint_database,
        fingerprint_schema=fingerprint_schema,
        language=FunctionLanguage.PYTHON,
        runtime_version=runtime_version,
        entry_point=entry_point,
        packages=packages,
        replay_on_change=_parse_optional_function_header(
            header_values=header_values,
            key="replay_on_change",
            effective_vars=effective_vars,
            relative_path=python_function_file.relative_path,
            language="Python",
        ),
    )


def _parse_function_arguments(
    *,
    function_file: DiscoveredSqlFunctionFile,
    effective_vars: dict[str, object],
) -> tuple[FunctionArgument, ...]:
    raw_arguments: object | None = function_file.header_values.get("arguments")
    if raw_arguments is None:
        return ()
    if not isinstance(raw_arguments, dict):
        raise CompileInputError(
            f"SQL function file {function_file.relative_path} arguments must be a map"
        )
    arguments: list[FunctionArgument] = []
    argument_name: object
    argument_type: object
    for argument_name, argument_type in raw_arguments.items():
        if not isinstance(argument_name, str) or not argument_name.strip():
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} has an invalid argument name"
            )
        if not isinstance(argument_type, str) or not argument_type.strip():
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} argument '{argument_name}' "
                "must declare a type"
            )
        expanded_type: str = _expand_function_header_value(
            raw_value=argument_type.strip(),
            effective_vars=effective_vars,
            context_label=(
                f"SQL function {function_file.relative_path} argument '{argument_name}' type"
            ),
        )
        arguments.append(FunctionArgument(name=argument_name.strip(), type=expanded_type))
    return tuple(arguments)


def _parse_python_function_arguments(
    *, function_file: DiscoveredPythonFunctionFile, effective_vars: dict[str, object]
) -> tuple[FunctionArgument, ...]:
    raw_arguments: object | None = function_file.header_values.get("arguments")
    if raw_arguments is None:
        return ()
    if not isinstance(raw_arguments, dict):
        raise CompileInputError(
            f"Python function file {function_file.relative_path} arguments must be a map"
        )
    arguments: list[FunctionArgument] = []
    argument_name: object
    argument_type: object
    for argument_name, argument_type in raw_arguments.items():
        if not isinstance(argument_name, str) or not argument_name.strip():
            raise CompileInputError(
                f"Python function file {function_file.relative_path} has an invalid argument name"
            )
        if not isinstance(argument_type, str) or not argument_type.strip():
            raise CompileInputError(
                f"Python function file {function_file.relative_path} argument '{argument_name}' "
                "must declare a type"
            )
        expanded_type: str = _expand_function_header_value(
            raw_value=argument_type.strip(),
            effective_vars=effective_vars,
            context_label=(
                f"Python function {function_file.relative_path} argument '{argument_name}' type"
            ),
        )
        arguments.append(FunctionArgument(name=argument_name.strip(), type=expanded_type))
    return tuple(arguments)


def _parse_sql_function_returns(
    *,
    raw_returns: object,
    function_file: DiscoveredSqlFunctionFile,
    effective_vars: dict[str, object],
) -> tuple[str, tuple[FunctionReturnColumn, ...]]:
    if isinstance(raw_returns, str) and raw_returns.strip():
        returns: str = _expand_function_header_value(
            raw_value=raw_returns.strip(),
            effective_vars=effective_vars,
            context_label=f"SQL function {function_file.relative_path} returns",
        )
        return returns, ()
    if isinstance(raw_returns, dict) and set(raw_returns) == TABLE_FUNCTION_RETURN_KEYS:
        table_returns: dict[str, object] = cast(dict[str, object], raw_returns)
        raw_columns: object = table_returns["table"]
        if not isinstance(raw_columns, dict) or not raw_columns:
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} returns table must declare "
                "at least one column"
            )
        columns: list[FunctionReturnColumn] = []
        column_name: object
        column_type: object
        for column_name, column_type in raw_columns.items():
            if not isinstance(column_name, str) or not column_name.strip():
                raise CompileInputError(
                    f"SQL function file {function_file.relative_path} has an invalid return "
                    "column name"
                )
            if not isinstance(column_type, str) or not column_type.strip():
                raise CompileInputError(
                    f"SQL function file {function_file.relative_path} return column "
                    f"'{column_name}' must declare a type"
                )
            expanded_type: str = _expand_function_header_value(
                raw_value=column_type.strip(),
                effective_vars=effective_vars,
                context_label=(
                    f"SQL function {function_file.relative_path} return column '{column_name}' type"
                ),
            )
            columns.append(FunctionReturnColumn(name=column_name.strip(), type=expanded_type))
        return "TABLE", tuple(columns)
    raise CompileInputError(
        f"SQL function file {function_file.relative_path} returns must be a type string or "
        "table column declaration"
    )


def _parse_required_string_header(
    *, header_values: dict[str, object], key: str, relative_path: Path, language: str
) -> str:
    raw_value: object | None = header_values.get(key)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise CompileInputError(f"{language} function file {relative_path} must declare {key}")
    return raw_value.strip()


def _parse_optional_function_header(
    *,
    header_values: dict[str, object],
    key: str,
    effective_vars: dict[str, object],
    relative_path: Path,
    language: str,
) -> str | None:
    raw_value: object | None = header_values.get(key)
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise CompileInputError(f"{language} function file {relative_path} {key} must be a string")
    return _expand_function_header_value(
        raw_value=raw_value.strip(),
        effective_vars=effective_vars,
        context_label=f"{language} function {relative_path} {key}",
    )


def _parse_python_packages(*, raw_packages: object | None, relative_path: Path) -> tuple[str, ...]:
    if raw_packages is None:
        return ()
    if not isinstance(raw_packages, list | tuple):
        raise CompileInputError(f"Python function file {relative_path} packages must be a list")
    packages: list[str] = []
    package: object
    for package in raw_packages:
        if not isinstance(package, str) or not package.strip():
            raise CompileInputError(
                f"Python function file {relative_path} packages entries must be non-empty strings"
            )
        packages.append(package.strip())
    return tuple(packages)


def _expand_function_header_value(
    *, raw_value: str, effective_vars: dict[str, object], context_label: str
) -> str:
    return str(
        expand_template_data(
            value=raw_value,
            variables=effective_vars,
            context_values={},
            context_label=context_label,
            allow_context=False,
            preserve_context_tokens=True,
            preserve_unknown_context=False,
        )
    )


def validate_native_type(*, type_sql: str, adapter_name: str, context: str) -> None:
    """Validate an adapter-native type string with SQL analysis when a dialect is known."""

    dialect_by_adapter: dict[str, str] = {
        "duckdb": "duckdb",
        "bigquery": "bigquery",
        "snowflake": "snowflake",
        "databricks": "databricks",
    }
    dialect: str | None = dialect_by_adapter.get(adapter_name)
    if dialect is None:
        return
    polyglot_module: Any | None = import_polyglot()
    if polyglot_module is None:
        return
    try:
        polyglot_module.parse_data_type(type_sql, dialect=dialect)
    except Exception as error:
        raise CompileInputError(
            f"{context} type '{type_sql}' is not valid for adapter '{adapter_name}' "
            f"SQL analysis dialect '{dialect}': {error}"
        ) from error


def _resolve_function_namespace(
    *,
    defaults: DefaultsConfig,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> tuple[str | None, str | None]:
    database: str | None = defaults.database
    schema: str | None = defaults.schema
    if target_config is not None:
        if target_config.database is not None:
            database = _expand_function_environment_value(
                raw_value=target_config.database,
                effective_vars=effective_vars,
                context_label="environment database",
            )
        if target_config.schema is not None:
            schema = _expand_function_environment_value(
                raw_value=target_config.schema,
                effective_vars=effective_vars,
                context_label="environment schema",
            )
    return database, schema


def _expand_function_environment_value(
    *, raw_value: str, effective_vars: dict[str, object], context_label: str
) -> str | None:
    if raw_value == PRESERVE_TARGET_VALUE:
        return None
    return str(
        expand_template_data(
            value=raw_value,
            variables=effective_vars,
            context_values={},
            context_label=context_label,
            allow_context=False,
            preserve_context_tokens=True,
            preserve_unknown_context=False,
        )
    )
