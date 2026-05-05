"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from sqlbuild.compiler.compile.constants import (
    AUDIT_DIRECTORY_NAME,
    GENERIC_AUDIT_DIRECTORY_NAME,
    GENERIC_AUDIT_QUOTED_PARAMETER_PATTERN,
    GENERIC_AUDIT_RAW_PARAMETER_PATTERN,
    MACRO_CALL_PATTERN,
    PRESERVE_ENVIRONMENT_VALUE,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.macros import (
    expand_sql_macros,
    load_project_macros,
)
from sqlbuild.compiler.compile.helpers.model_config_validation import (
    validate_custom_materialization_config,
    validate_incremental_config,
    validate_non_incremental_config,
    validate_placeholder_config,
)
from sqlbuild.compiler.compile.helpers.refs import extract_sql_references
from sqlbuild.compiler.compile.helpers.sql_vars import (
    substitute_sql_vars,
    validate_var_macro_collision,
)
from sqlbuild.compiler.compile.helpers.sqlglot_validation import (
    validate_function_sql_syntax,
    validate_hook_sql_syntax,
    validate_source_expression_syntax,
    validate_sql_syntax,
)
from sqlbuild.compiler.compile.helpers.templating import (
    expand_effective_vars,
    expand_template_data,
)
from sqlbuild.compiler.compile.helpers.tests import extract_sql_test_ctes
from sqlbuild.compiler.compile.models import (
    CompileAuditInput,
    CompileModelConfig,
    CompileModelInput,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlFunctionInput,
    CompileSqlReference,
    CompileSqlTestCtes,
    CompileSqlTestInput,
    FunctionArgument,
    FunctionReturnColumn,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompileContextKey,
    FunctionLanguage,
    SqlReferenceKind,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredProjectInputs,
    DiscoveredPythonFunctionFile,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSourceFile,
    DiscoveredSqlFunctionFile,
    DiscoveredSqlModelFile,
    DiscoveredSqlTestBlock,
    DiscoveredSqlTestFile,
)
from sqlbuild.compiler.shared.constants import SCHEMA_FILE_NAME, SEED_FILE_SUFFIX
from sqlbuild.spec.models.project import (
    ClonePolicy,
    DefaultsConfig,
    EnvironmentConfig,
    LocalClonePolicy,
    LocalConfig,
    LocalEnvironmentConfig,
    ProjectConfig,
    SettingsConfig,
)
from sqlbuild.spec.models.schema import (
    SchemaAuditInstance,
    SchemaColumn,
    SchemaModelEntry,
    SchemaSeedEntry,
)
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry


def build_model_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    effective_vars: dict[str, str],
    effective_settings: SettingsConfig,
    environment_config: EnvironmentConfig | None,
    effective_environment_name: str | None,
    run_id: str,
    macro_context: MacroContext,
    no_sql_validation: bool = False,
) -> tuple[CompileModelInput, ...]:
    """Attach schema metadata to discovered model files."""

    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)
    validate_var_macro_collision(effective_vars=effective_vars, loaded_macros=loaded_macros)
    known_model_names: set[str] = build_known_ref_names(discovered_inputs)
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    known_function_names: set[str] = build_known_function_names(discovered_inputs)
    known_table_function_names: set[str] = build_known_table_function_names(discovered_inputs)
    custom_materialization_names: frozenset[str] = frozenset(
        mf.name for mf in discovered_inputs.materialization_files
    )
    model_inputs: list[CompileModelInput] = []
    model_file: DiscoveredSqlModelFile
    for model_file in discovered_inputs.model_files:
        matched_path_default: str | None = find_matching_path_default(
            model_file=model_file,
            path_defaults=discovered_inputs.project_config.path_defaults,
        )
        effective_config: CompileModelConfig = build_model_config(
            defaults=discovered_inputs.project_config.defaults,
            path_defaults=discovered_inputs.project_config.path_defaults,
            matched_path_default=matched_path_default,
            model_header_values=model_file.header_values,
            effective_vars=effective_vars,
            environment_config=environment_config,
            model_name=model_file.file_path.stem,
            effective_environment_name=effective_environment_name,
            run_id=run_id,
        )
        var_substituted_sql: str = substitute_sql_vars(
            sql=model_file.query_sql,
            file_path=model_file.file_path,
            effective_vars=effective_vars,
        )
        expanded_query_sql: str = expand_sql_macros(
            sql=var_substituted_sql,
            file_path=model_file.file_path,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
        )
        raw_placeholders: object | None = effective_config.values.get("placeholders")
        sql_validation_placeholders: dict[str, str] | None = (
            {str(k): str(v) for k, v in raw_placeholders.items()}
            if isinstance(raw_placeholders, dict)
            else None
        )
        if not no_sql_validation and _is_sql_validation_enabled(
            project_setting=effective_settings.sql_validation,
            model_config=effective_config,
        ):
            validate_sql_syntax(
                query_sql=expanded_query_sql,
                model_name=model_file.file_path.stem,
                file_path=model_file.file_path,
                placeholders=sql_validation_placeholders,
            )
        references: tuple[CompileSqlReference, ...] = extract_sql_references(expanded_query_sql)
        validate_model_references(
            references=references,
            model_file=model_file,
            known_model_names=known_model_names,
            known_source_names=known_source_names,
            known_function_names=known_function_names,
            known_table_function_names=known_table_function_names,
            has_dbt_manifest=discovered_inputs.dbt_manifest_file is not None,
        )
        validate_incremental_config(
            config=effective_config,
            model_name=model_file.file_path.stem,
            ref_count=len(references),
            known_input_names=frozenset(reference.ref_name for reference in references),
        )
        validate_non_incremental_config(
            config=effective_config,
            model_name=model_file.file_path.stem,
        )
        validate_custom_materialization_config(
            config=effective_config,
            model_name=model_file.file_path.stem,
            custom_materialization_names=custom_materialization_names,
        )
        validate_placeholder_config(
            config=effective_config,
            model_name=model_file.file_path.stem,
            query_sql=expanded_query_sql,
            custom_materialization_names=custom_materialization_names,
        )
        expanded_config: CompileModelConfig = CompileModelConfig(
            values=expand_model_hook_macros(
                values=effective_config.values,
                file_path=model_file.file_path,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
            ),
            matched_path_default=effective_config.matched_path_default,
        )
        if not no_sql_validation and _is_sql_validation_enabled(
            project_setting=effective_settings.sql_validation,
            model_config=effective_config,
        ):
            hook_name: str
            for hook_name in ("pre_hook", "post_hook"):
                validate_hook_sql_syntax(
                    value=expanded_config.values.get(hook_name),
                    hook_name=hook_name,
                    model_name=model_file.file_path.stem,
                    file_path=model_file.file_path,
                    placeholders=sql_validation_placeholders,
                )
        schema_match: tuple[SchemaModelEntry, DiscoveredSchemaFile] | None = (
            find_schema_model_match(
                model_file=model_file,
                schema_files=discovered_inputs.schema_files,
            )
        )
        if schema_match is None:
            model_inputs.append(
                CompileModelInput(
                    model_file=model_file,
                    config=expanded_config,
                    query_sql=expanded_query_sql,
                    macro_source_sql=var_substituted_sql,
                    references=references,
                )
            )
            continue

        schema_entry: SchemaModelEntry = schema_match[0]
        schema_file: DiscoveredSchemaFile = schema_match[1]
        config_with_schema_tags: CompileModelConfig = _merge_schema_tags(
            config=expanded_config, schema_entry=schema_entry
        )
        model_inputs.append(
            CompileModelInput(
                model_file=model_file,
                config=config_with_schema_tags,
                query_sql=expanded_query_sql,
                macro_source_sql=var_substituted_sql,
                references=references,
                schema_entry=schema_entry,
                schema_file=schema_file,
            )
        )

    validate_declared_schema_models_are_attached(
        model_inputs=tuple(model_inputs),
        schema_files=discovered_inputs.schema_files,
    )
    return tuple(model_inputs)


def build_seed_inputs(discovered_inputs: DiscoveredProjectInputs) -> tuple[CompileSeedInput, ...]:
    """Attach seed schema metadata to discovered seed files."""

    seed_schema_matches: dict[str, tuple[SchemaSeedEntry, DiscoveredSchemaFile]] = {}
    schema_file: DiscoveredSchemaFile
    for schema_file in discovered_inputs.schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            seed_schema_matches[seed_entry.name] = (seed_entry, schema_file)

    seed_inputs: list[CompileSeedInput] = []
    seed_file: DiscoveredSeedFile
    for seed_file in discovered_inputs.seed_files:
        if seed_file.file_path.suffix != SEED_FILE_SUFFIX:
            continue

        seed_name: str = seed_file.file_path.stem
        schema_match: tuple[SchemaSeedEntry, DiscoveredSchemaFile] | None = seed_schema_matches.get(
            seed_name
        )
        if schema_match is None:
            raise CompileInputError(
                f"Seed file {seed_file.relative_path} has no matching seed declaration in "
                f"{SCHEMA_FILE_NAME}"
            )

        seed_inputs.append(
            CompileSeedInput(
                seed_file=seed_file,
                schema_entry=schema_match[0],
                schema_file=schema_match[1],
            )
        )

    return tuple(seed_inputs)


def build_sql_function_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    effective_vars: dict[str, str],
    effective_settings: SettingsConfig,
    environment_config: EnvironmentConfig | None,
    adapter_name: str,
    macro_context: MacroContext,
    no_sql_validation: bool = False,
) -> tuple[CompileSqlFunctionInput, ...]:
    """Attach and validate SQL function metadata."""

    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)
    known_model_names: set[str] = build_known_ref_names(discovered_inputs)
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    known_function_names: set[str] = build_known_function_names(discovered_inputs)
    known_table_function_names: set[str] = build_known_table_function_names(discovered_inputs)
    database, schema = _resolve_function_namespace(
        defaults=discovered_inputs.project_config.defaults,
        environment_config=environment_config,
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
        var_substituted_body_sql: str = substitute_sql_vars(
            sql=function_file.body_sql,
            file_path=function_file.file_path,
            effective_vars=effective_vars,
        )
        expanded_body_sql: str = expand_sql_macros(
            sql=var_substituted_body_sql,
            file_path=function_file.file_path,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
        )
        if not no_sql_validation and effective_settings.sql_validation:
            argument: FunctionArgument
            for argument in arguments:
                validate_native_type(
                    argument.type,
                    adapter_name=adapter_name,
                    context=(
                        f"SQL function {function_file.relative_path} argument '{argument.name}'"
                    ),
                )
            if return_columns:
                return_column: FunctionReturnColumn
                for return_column in return_columns:
                    validate_native_type(
                        return_column.type,
                        adapter_name=adapter_name,
                        context=(
                            f"SQL function {function_file.relative_path} return column "
                            f"'{return_column.name}'"
                        ),
                    )
            else:
                validate_native_type(
                    returns,
                    adapter_name=adapter_name,
                    context=f"SQL function {function_file.relative_path} return type",
                )
            validate_function_sql_syntax(
                body_sql=expanded_body_sql,
                function_name=function_name,
                file_path=function_file.file_path,
            )
        references: tuple[CompileSqlReference, ...] = extract_sql_references(expanded_body_sql)
        validate_function_references(
            references=references,
            function_file=function_file,
            known_model_names=known_model_names,
            known_source_names=known_source_names,
            known_function_names=known_function_names,
            known_table_function_names=known_table_function_names,
            has_dbt_manifest=discovered_inputs.dbt_manifest_file is not None,
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
            )
        )
    python_function_file: DiscoveredPythonFunctionFile
    for python_function_file in discovered_inputs.python_function_files:
        function_name = python_function_file.file_path.stem
        if function_name in known_names:
            raise CompileInputError(f"Duplicate function name '{function_name}'")
        known_names.add(function_name)
        header_values = python_function_file.header_values
        raw_returns = header_values.get("returns")
        if not isinstance(raw_returns, str) or not raw_returns.strip():
            raise CompileInputError(
                f"Python function file {python_function_file.relative_path} must declare returns"
            )
        arguments: tuple[FunctionArgument, ...] = _parse_python_function_arguments(
            python_function_file, effective_vars
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
        raw_database = header_values.get("database")
        raw_schema = header_values.get("schema")
        function_database = (
            _expand_function_header_value(
                raw_value=raw_database,
                effective_vars=effective_vars,
                context_label=f"Python function {python_function_file.relative_path} database",
            )
            if isinstance(raw_database, str)
            else database
        )
        function_schema = (
            _expand_function_header_value(
                raw_value=raw_schema,
                effective_vars=effective_vars,
                context_label=f"Python function {python_function_file.relative_path} schema",
            )
            if isinstance(raw_schema, str)
            else schema
        )
        if not no_sql_validation and effective_settings.sql_validation:
            for argument in arguments:
                validate_native_type(
                    argument.type,
                    adapter_name=adapter_name,
                    context=(
                        f"Python function {python_function_file.relative_path} "
                        f"argument '{argument.name}'"
                    ),
                )
            validate_native_type(
                returns,
                adapter_name=adapter_name,
                context=f"Python function {python_function_file.relative_path} return type",
            )
        compile_input: CompileSqlFunctionInput = CompileSqlFunctionInput(
            function_file=python_function_file,
            name=function_name,
            arguments=arguments,
            returns=returns,
            body_sql=python_function_file.body_python,
            database=function_database,
            schema=function_schema,
            language=FunctionLanguage.PYTHON,
            runtime_version=runtime_version,
            entry_point=entry_point,
            packages=packages,
        )
        function_inputs.append(compile_input)
    return tuple(function_inputs)


def _parse_function_arguments(
    *,
    function_file: DiscoveredSqlFunctionFile,
    effective_vars: dict[str, str],
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
    function_file: DiscoveredPythonFunctionFile, effective_vars: dict[str, str]
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
    effective_vars: dict[str, str],
) -> tuple[str, tuple[FunctionReturnColumn, ...]]:
    if isinstance(raw_returns, str) and raw_returns.strip():
        returns: str = _expand_function_header_value(
            raw_value=raw_returns.strip(),
            effective_vars=effective_vars,
            context_label=f"SQL function {function_file.relative_path} returns",
        )
        return returns, ()
    if isinstance(raw_returns, dict) and set(raw_returns) == {"table"}:
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
    *, raw_value: str, effective_vars: dict[str, str], context_label: str
) -> str:
    return str(
        expand_template_data(
            raw_value,
            variables=effective_vars,
            context_values={},
            context_label=context_label,
            allow_context=False,
            preserve_context_tokens=True,
            preserve_unknown_context=False,
        )
    )


def validate_native_type(type_sql: str, *, adapter_name: str, context: str) -> None:
    """Validate an adapter-native type string with SQLGlot when a dialect is known."""

    dialect_by_adapter: dict[str, str] = {
        "duckdb": "duckdb",
        "bigquery": "bigquery",
        "snowflake": "snowflake",
        "databricks": "databricks",
    }
    dialect: str | None = dialect_by_adapter.get(adapter_name)
    if dialect is None:
        return
    try:
        import sqlglot

        sqlglot.parse_one(
            f"CREATE TABLE __sqlbuild_type_check__ (__value__ {type_sql})",
            read=dialect,
        )
    except Exception as error:
        raise CompileInputError(
            f"{context} type '{type_sql}' is not valid for adapter '{adapter_name}' "
            f"SQLGlot dialect '{dialect}': {error}"
        ) from error


def _resolve_function_namespace(
    *,
    defaults: DefaultsConfig,
    environment_config: EnvironmentConfig | None,
    effective_vars: dict[str, str],
) -> tuple[str | None, str | None]:
    database: str | None = defaults.database
    schema: str | None = defaults.schema
    if environment_config is not None:
        if environment_config.database is not None:
            database = _expand_function_environment_value(
                raw_value=environment_config.database,
                effective_vars=effective_vars,
                context_label="environment database",
            )
        if environment_config.schema is not None:
            schema = _expand_function_environment_value(
                raw_value=environment_config.schema,
                effective_vars=effective_vars,
                context_label="environment schema",
            )
    return database, schema


def _expand_function_environment_value(
    *, raw_value: str, effective_vars: dict[str, str], context_label: str
) -> str | None:
    if raw_value == PRESERVE_ENVIRONMENT_VALUE:
        return None
    return str(
        expand_template_data(
            raw_value,
            variables=effective_vars,
            context_values={},
            context_label=context_label,
            allow_context=False,
            preserve_context_tokens=True,
            preserve_unknown_context=False,
        )
    )


def build_source_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    effective_settings: SettingsConfig,
    no_sql_validation: bool = False,
) -> tuple[CompileSourceInput, ...]:
    """Normalize discovered source declarations into one collection."""

    source_inputs: list[CompileSourceInput] = []
    sql_validation_enabled: bool = effective_settings.sql_validation and not no_sql_validation
    source_file: DiscoveredSourceFile
    for source_file in discovered_inputs.source_files:
        source_entry: SourceEntry
        for source_entry in source_file.source_entries:
            source_expression: str | None = source_entry.expression
            should_validate_expression: bool = (
                source_expression is not None and sql_validation_enabled
            )
            if should_validate_expression and source_expression is not None:
                validate_source_expression_syntax(
                    expression=source_expression,
                    source_name=source_entry.name,
                    file_path=source_file.file_path,
                )
            source_inputs.append(
                CompileSourceInput(
                    source_entry=source_entry,
                    source_file=source_file,
                )
            )
    return tuple(source_inputs)


def build_test_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    effective_vars: dict[str, str] | None = None,
    macro_context: MacroContext,
) -> tuple[CompileSqlTestInput, ...]:
    """Build compile-time test inputs from discovered SQL-native test blocks."""

    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)
    vars_for_substitution: dict[str, str] = effective_vars or {}
    known_model_names: set[str] = build_known_ref_names(discovered_inputs)
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    test_inputs: list[CompileSqlTestInput] = []
    test_file: DiscoveredSqlTestFile
    for test_file in discovered_inputs.test_files:
        test_block: DiscoveredSqlTestBlock
        for test_block in test_file.blocks:
            var_substituted_body: str = substitute_sql_vars(
                sql=test_block.sql_body,
                file_path=test_file.file_path,
                effective_vars=vars_for_substitution,
            )
            expanded_sql_body: str = expand_sql_macros(
                sql=var_substituted_body,
                file_path=test_file.file_path,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
            )
            test_ctes: CompileSqlTestCtes = extract_sql_test_ctes(
                sql=expanded_sql_body,
                file_label=str(test_file.relative_path),
            )
            validate_test_ctes(
                test_ctes=test_ctes,
                test_file=test_file,
                known_model_names=known_model_names,
                known_source_names=known_source_names,
                loaded_macros=loaded_macros,
            )
            test_inputs.append(
                CompileSqlTestInput(
                    test_file=test_file,
                    test_block=test_block,
                    sql_body=expanded_sql_body,
                    authored_ctes=test_ctes.authored_ctes,
                    macro_mocks=test_ctes.macro_mocks,
                    mock_model_names=test_ctes.mock_model_names,
                    mock_source_names=test_ctes.mock_source_names,
                    expected_model_names=test_ctes.expected_model_names,
                )
            )
    return tuple(test_inputs)


def validate_test_ctes(
    *,
    test_ctes: CompileSqlTestCtes,
    test_file: DiscoveredSqlTestFile,
    known_model_names: set[str],
    known_source_names: set[str],
    loaded_macros: dict[str, LoadedMacro],
) -> None:
    """Validate SQL-native test CTE targets against discovered inputs."""

    mock_model_name: str
    for mock_model_name in test_ctes.mock_model_names:
        if mock_model_name not in known_model_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} mocks unknown model '{mock_model_name}'"
            )
    mock_source_name: str
    for mock_source_name in test_ctes.mock_source_names:
        if mock_source_name not in known_source_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} mocks unknown source '{mock_source_name}'"
            )
    macro_mock_name: str
    for macro_mock_name in test_ctes.macro_mocks:
        if macro_mock_name not in loaded_macros:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} mocks unknown macro '{macro_mock_name}'"
            )
    expected_model_name: str
    for expected_model_name in test_ctes.expected_model_names:
        if expected_model_name not in known_model_names:
            raise CompileInputError(
                f"SQL test file {test_file.relative_path} expects unknown model "
                f"'{expected_model_name}'"
            )


def build_audit_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    effective_settings: SettingsConfig,
    model_inputs: tuple[CompileModelInput, ...],
    source_inputs: tuple[CompileSourceInput, ...],
    macro_context: MacroContext,
) -> tuple[CompileAuditInput, ...]:
    """Build compile-time audit inputs from discovered SQL audit blocks."""

    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)
    known_model_names: set[str] = build_known_ref_names(discovered_inputs)
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    generic_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]] = (
        index_generic_audit_definitions(discovered_inputs.audit_files)
    )
    default_audit_severity: str | None = effective_settings.default_audit_severity
    default_audit_run_scope: str | None = effective_settings.default_audit_run_scope
    audit_inputs: list[CompileAuditInput] = []
    audit_file: DiscoveredAuditFile
    for audit_file in discovered_inputs.audit_files:
        if is_generic_audit_file(audit_file):
            continue
        audit_block: DiscoveredAuditBlock
        for audit_block in audit_file.blocks:
            expanded_sql_body: str = expand_sql_macros(
                sql=audit_block.sql_body,
                file_path=audit_file.file_path,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
            )
            references: tuple[CompileSqlReference, ...] = extract_sql_references(expanded_sql_body)
            validate_audit_references(
                references=references,
                audit_file=audit_file,
                known_model_names=known_model_names,
                known_source_names=known_source_names,
            )
            header_severity: str | None = _str_from_dict(audit_block.header_values, "severity")
            header_run_scope: str | None = _str_from_dict(audit_block.header_values, "run_scope")
            resolved_severity: str = resolve_audit_severity(
                instance_severity=header_severity,
                default_severity=default_audit_severity,
                audit_label=str(audit_file.relative_path),
            )
            resolved_run_scope: str = resolve_audit_run_scope(
                instance_run_scope=header_run_scope,
                default_run_scope=default_audit_run_scope,
            )
            audit_inputs.append(
                CompileAuditInput(
                    audit_file=audit_file,
                    audit_block=audit_block,
                    sql_body=expanded_sql_body,
                    references=references,
                    severity=resolved_severity,
                    run_scope=resolved_run_scope,
                )
            )
    model_input: CompileModelInput
    for model_input in model_inputs:
        if model_input.schema_entry is None or model_input.schema_file is None:
            continue
        audit_inputs.extend(
            build_model_attached_audit_inputs(
                model_input=model_input,
                schema_file=model_input.schema_file,
                generic_audit_definitions=generic_audit_definitions,
                loaded_macros=loaded_macros,
                known_model_names=known_model_names,
                known_source_names=known_source_names,
                default_audit_severity=default_audit_severity,
                default_audit_run_scope=default_audit_run_scope,
                macro_context=macro_context,
            )
        )
    source_input: CompileSourceInput
    for source_input in source_inputs:
        audit_inputs.extend(
            build_source_attached_audit_inputs(
                source_input=source_input,
                generic_audit_definitions=generic_audit_definitions,
                loaded_macros=loaded_macros,
                known_model_names=known_model_names,
                known_source_names=known_source_names,
                default_audit_severity=default_audit_severity,
                default_audit_run_scope=default_audit_run_scope,
                macro_context=macro_context,
            )
        )
    return tuple(audit_inputs)


def build_model_attached_audit_inputs(
    *,
    model_input: CompileModelInput,
    schema_file: DiscoveredSchemaFile,
    generic_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]],
    loaded_macros: dict[str, LoadedMacro],
    known_model_names: set[str],
    known_source_names: set[str],
    default_audit_severity: str | None,
    default_audit_run_scope: str | None,
    macro_context: MacroContext,
) -> tuple[CompileAuditInput, ...]:
    """Render schema-attached model audits into compile audit inputs."""

    assert model_input.schema_entry is not None
    attached_audit_inputs: list[CompileAuditInput] = []
    audit_instance: SchemaAuditInstance
    for audit_instance in model_input.schema_entry.audits:
        attached_audit_inputs.append(
            build_attached_audit_input(
                audit_instance=audit_instance,
                owner_file=schema_file.relative_path,
                generic_audit_definitions=generic_audit_definitions,
                implicit_arguments={"model": model_input.model_file.file_path.stem},
                attached_target_kind=AttachedAuditTargetKind.MODEL,
                attached_target_name=model_input.model_file.file_path.stem,
                attached_column_name=None,
                loaded_macros=loaded_macros,
                known_model_names=known_model_names,
                known_source_names=known_source_names,
                default_audit_severity=default_audit_severity,
                default_audit_run_scope=default_audit_run_scope,
                macro_context=macro_context,
            )
        )
    column_entry: SchemaColumn
    for column_entry in model_input.schema_entry.columns:
        for audit_instance in column_entry.audits:
            attached_audit_inputs.append(
                build_attached_audit_input(
                    audit_instance=audit_instance,
                    owner_file=schema_file.relative_path,
                    generic_audit_definitions=generic_audit_definitions,
                    implicit_arguments={
                        "model": model_input.model_file.file_path.stem,
                        "column": column_entry.name,
                    },
                    attached_target_kind=AttachedAuditTargetKind.MODEL,
                    attached_target_name=model_input.model_file.file_path.stem,
                    attached_column_name=column_entry.name,
                    loaded_macros=loaded_macros,
                    known_model_names=known_model_names,
                    known_source_names=known_source_names,
                    default_audit_severity=default_audit_severity,
                    default_audit_run_scope=default_audit_run_scope,
                    macro_context=macro_context,
                )
            )
    return tuple(attached_audit_inputs)


def build_source_attached_audit_inputs(
    *,
    source_input: CompileSourceInput,
    generic_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]],
    loaded_macros: dict[str, LoadedMacro],
    known_model_names: set[str],
    known_source_names: set[str],
    default_audit_severity: str | None,
    default_audit_run_scope: str | None,
    macro_context: MacroContext,
) -> tuple[CompileAuditInput, ...]:
    """Render source-attached audits into compile audit inputs."""

    attached_audit_inputs: list[CompileAuditInput] = []
    audit_instance: SchemaAuditInstance
    for audit_instance in source_input.source_entry.audits:
        attached_audit_inputs.append(
            build_attached_audit_input(
                audit_instance=audit_instance,
                owner_file=source_input.source_file.relative_path,
                generic_audit_definitions=generic_audit_definitions,
                implicit_arguments={"source": source_input.source_entry.name},
                attached_target_kind=AttachedAuditTargetKind.SOURCE,
                attached_target_name=source_input.source_entry.name,
                attached_column_name=None,
                loaded_macros=loaded_macros,
                known_model_names=known_model_names,
                known_source_names=known_source_names,
                default_audit_severity=default_audit_severity,
                default_audit_run_scope=default_audit_run_scope,
                macro_context=macro_context,
            )
        )
    column_entry: SourceColumnEntry
    for column_entry in source_input.source_entry.columns:
        for audit_instance in column_entry.audits:
            attached_audit_inputs.append(
                build_attached_audit_input(
                    audit_instance=audit_instance,
                    owner_file=source_input.source_file.relative_path,
                    generic_audit_definitions=generic_audit_definitions,
                    implicit_arguments={
                        "source": source_input.source_entry.name,
                        "column": column_entry.name,
                    },
                    attached_target_kind=AttachedAuditTargetKind.SOURCE,
                    attached_target_name=source_input.source_entry.name,
                    attached_column_name=column_entry.name,
                    loaded_macros=loaded_macros,
                    known_model_names=known_model_names,
                    known_source_names=known_source_names,
                    default_audit_severity=default_audit_severity,
                    default_audit_run_scope=default_audit_run_scope,
                    macro_context=macro_context,
                )
            )
    return tuple(attached_audit_inputs)


def build_attached_audit_input(
    *,
    audit_instance: SchemaAuditInstance,
    owner_file: Path,
    generic_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]],
    implicit_arguments: dict[str, object],
    attached_target_kind: str,
    attached_target_name: str,
    attached_column_name: str | None,
    loaded_macros: dict[str, LoadedMacro],
    known_model_names: set[str],
    known_source_names: set[str],
    default_audit_severity: str | None,
    default_audit_run_scope: str | None,
    macro_context: MacroContext,
) -> CompileAuditInput:
    """Render one attached generic audit instance into a compile audit input."""

    definition: tuple[DiscoveredAuditFile, DiscoveredAuditBlock] | None = (
        generic_audit_definitions.get(audit_instance.definition_name)
    )
    if definition is None:
        raise CompileInputError(
            f"{owner_file} references unknown generic audit '{audit_instance.definition_name}'"
        )
    merged_arguments: dict[str, object] = merge_audit_arguments(
        owner_file=owner_file,
        definition_name=audit_instance.definition_name,
        implicit_arguments=implicit_arguments,
        explicit_arguments=audit_instance.arguments,
    )
    rendered_sql_body: str = render_generic_audit_sql(
        sql=definition[1].sql_body,
        arguments=merged_arguments,
        owner_file=owner_file,
        definition_name=audit_instance.definition_name,
    )
    expanded_sql_body: str = expand_sql_macros(
        sql=rendered_sql_body,
        file_path=definition[0].file_path,
        loaded_macros=loaded_macros,
        macro_context=macro_context,
    )
    references: tuple[CompileSqlReference, ...] = extract_sql_references(expanded_sql_body)
    validate_audit_references(
        references=references,
        audit_file=definition[0],
        known_model_names=known_model_names,
        known_source_names=known_source_names,
    )
    audit_label: str = f"{owner_file} audit '{audit_instance.definition_name}'"
    resolved_severity: str = resolve_audit_severity(
        instance_severity=audit_instance.severity,
        default_severity=default_audit_severity,
        audit_label=audit_label,
    )
    resolved_run_scope: str = resolve_audit_run_scope(
        instance_run_scope=audit_instance.run_scope,
        default_run_scope=default_audit_run_scope,
    )
    validate_model_attached_audit_references(
        references=references,
        attached_target_kind=attached_target_kind,
        attached_target_name=attached_target_name,
        audit_label=audit_label,
    )
    return CompileAuditInput(
        audit_file=definition[0],
        audit_block=definition[1],
        sql_body=expanded_sql_body,
        references=references,
        attached_target_kind=attached_target_kind,
        attached_target_name=attached_target_name,
        attached_column_name=attached_column_name,
        severity=resolved_severity,
        run_scope=resolved_run_scope,
    )


def index_generic_audit_definitions(
    audit_files: tuple[DiscoveredAuditFile, ...],
) -> dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]]:
    """Index generic audit definitions discovered under audits/generic/."""

    definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]] = {}
    audit_file: DiscoveredAuditFile
    for audit_file in audit_files:
        if not is_generic_audit_file(audit_file):
            continue
        if len(audit_file.blocks) != 1:
            raise CompileInputError(
                f"Generic audit definition {audit_file.relative_path} must contain exactly "
                "one AUDIT block"
            )
        definition_name: str = audit_file.file_path.stem
        if definition_name in definitions:
            raise CompileInputError(
                f"Duplicate generic audit definition found for '{definition_name}'"
            )
        definitions[definition_name] = (audit_file, audit_file.blocks[0])
    return definitions


def is_generic_audit_file(audit_file: DiscoveredAuditFile) -> bool:
    """Return whether a discovered audit file is a generic definition."""

    return audit_file.relative_path.parts[:2] == (
        AUDIT_DIRECTORY_NAME,
        GENERIC_AUDIT_DIRECTORY_NAME,
    )


def merge_audit_arguments(
    *,
    owner_file: Path,
    definition_name: str,
    implicit_arguments: dict[str, object],
    explicit_arguments: dict[str, object],
) -> dict[str, object]:
    """Merge implicit attached-audit arguments with explicit authored arguments."""

    merged_arguments: dict[str, object] = dict(implicit_arguments)
    argument_name: str
    argument_value: object
    for argument_name, argument_value in explicit_arguments.items():
        if (
            argument_name in implicit_arguments
            and implicit_arguments[argument_name] != argument_value
        ):
            raise CompileInputError(
                f"{owner_file} audit '{definition_name}' must not override implicit "
                f"{argument_name} from attached context"
            )
        merged_arguments[argument_name] = argument_value
    return merged_arguments


def render_generic_audit_sql(
    *,
    sql: str,
    arguments: dict[str, object],
    owner_file: Path,
    definition_name: str,
) -> str:
    """Render generic attached-audit parameters into executable SQL text."""

    rendered_sql: str = GENERIC_AUDIT_QUOTED_PARAMETER_PATTERN.sub(
        lambda match: render_generic_audit_argument(
            argument_name=match.group("name"),
            arguments=arguments,
            owner_file=owner_file,
            definition_name=definition_name,
            quoted=True,
        ),
        sql,
    )
    rendered_sql = GENERIC_AUDIT_RAW_PARAMETER_PATTERN.sub(
        lambda match: render_generic_audit_argument(
            argument_name=match.group("name"),
            arguments=arguments,
            owner_file=owner_file,
            definition_name=definition_name,
            quoted=False,
        ),
        rendered_sql,
    )
    return rendered_sql


def render_generic_audit_argument(
    *,
    argument_name: str,
    arguments: dict[str, object],
    owner_file: Path,
    definition_name: str,
    quoted: bool,
) -> str:
    """Render one generic attached-audit parameter value into SQL text."""

    if argument_name not in arguments:
        raise CompileInputError(
            f"{owner_file} is missing argument '{argument_name}' for generic audit "
            f"'{definition_name}'"
        )
    return render_generic_audit_argument_value(
        argument_value=arguments[argument_name],
        owner_file=owner_file,
        definition_name=definition_name,
        argument_name=argument_name,
        quoted=quoted,
    )


def render_generic_audit_argument_value(
    *,
    argument_value: object,
    owner_file: Path,
    definition_name: str,
    argument_name: str,
    quoted: bool,
) -> str:
    """Render one generic attached-audit argument value using raw or literal SQL rules."""

    if isinstance(argument_value, list | tuple):
        return ", ".join(
            render_generic_audit_argument_value(
                argument_value=item,
                owner_file=owner_file,
                definition_name=definition_name,
                argument_name=argument_name,
                quoted=quoted,
            )
            for item in argument_value
        )
    if isinstance(argument_value, bool):
        return "TRUE" if argument_value else "FALSE"
    if argument_value is None:
        return "NULL"
    if isinstance(argument_value, int | float):
        return str(argument_value)
    if isinstance(argument_value, str):
        if quoted:
            escaped_value: str = argument_value.replace("'", "''")
            return f"'{escaped_value}'"
        return argument_value
    raise CompileInputError(
        f"{owner_file} audit '{definition_name}' argument '{argument_name}' uses an "
        "unsupported value"
    )


def validate_model_references(
    *,
    references: tuple[CompileSqlReference, ...],
    model_file: DiscoveredSqlModelFile,
    known_model_names: set[str],
    known_source_names: set[str],
    known_function_names: set[str],
    known_table_function_names: set[str],
    has_dbt_manifest: bool,
) -> None:
    """Validate extracted model refs against discovered project inputs."""

    reference: CompileSqlReference
    for reference in references:
        if (
            reference.ref_kind == SqlReferenceKind.REF
            and reference.ref_name not in known_model_names
        ):
            raise CompileInputError(
                f"Model file {model_file.relative_path} references unknown model "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.SOURCE
            and reference.ref_name not in known_source_names
        ):
            raise CompileInputError(
                f"Model file {model_file.relative_path} references unknown source "
                f"'{reference.ref_name}'"
            )
        if reference.ref_kind == SqlReferenceKind.DBT_REF and not has_dbt_manifest:
            raise CompileInputError(
                f"Model file {model_file.relative_path} uses __dbt_ref('{reference.ref_name}') "
                "but no dbt manifest.json was discovered"
            )
        if (
            reference.ref_kind == SqlReferenceKind.UDF
            and reference.ref_name not in known_function_names
        ):
            raise CompileInputError(
                f"Model file {model_file.relative_path} references unknown SQL function "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.UDF
            and reference.ref_name in known_table_function_names
        ):
            raise CompileInputError(
                f"Model file {model_file.relative_path} references table function "
                f"'{reference.ref_name}' with __udf(); use __table_function() in SQL contexts "
                "that support table-valued functions"
            )
        if reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION:
            raise CompileInputError(
                f"Model file {model_file.relative_path} references table function "
                f"'{reference.ref_name}', but table functions are terminal resources and cannot "
                "be model dependencies"
            )


def validate_function_references(
    *,
    references: tuple[CompileSqlReference, ...],
    function_file: DiscoveredSqlFunctionFile,
    known_model_names: set[str],
    known_source_names: set[str],
    known_function_names: set[str],
    known_table_function_names: set[str],
    has_dbt_manifest: bool,
) -> None:
    """Validate extracted SQL function refs against discovered project inputs."""

    reference: CompileSqlReference
    for reference in references:
        if (
            reference.ref_kind == SqlReferenceKind.REF
            and reference.ref_name not in known_model_names
        ):
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references unknown model "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.SOURCE
            and reference.ref_name not in known_source_names
        ):
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references unknown source "
                f"'{reference.ref_name}'"
            )
        if reference.ref_kind == SqlReferenceKind.DBT_REF and not has_dbt_manifest:
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} uses "
                f"__dbt_ref('{reference.ref_name}') but no dbt manifest.json was discovered"
            )
        if (
            reference.ref_kind in {SqlReferenceKind.UDF, SqlReferenceKind.TABLE_FUNCTION}
            and reference.ref_name not in known_function_names
        ):
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references unknown SQL function "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.UDF
            and reference.ref_name in known_table_function_names
        ):
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references table function "
                f"'{reference.ref_name}' with __udf(); use __table_function()"
            )
        if (
            reference.ref_kind == SqlReferenceKind.TABLE_FUNCTION
            and reference.ref_name not in known_table_function_names
        ):
            raise CompileInputError(
                f"SQL function file {function_file.relative_path} references scalar function "
                f"'{reference.ref_name}' with __table_function(); use __udf() for scalar UDFs"
            )


def validate_audit_references(
    *,
    references: tuple[CompileSqlReference, ...],
    audit_file: DiscoveredAuditFile,
    known_model_names: set[str],
    known_source_names: set[str],
) -> None:
    """Validate extracted audit refs against discovered project inputs."""

    reference: CompileSqlReference
    for reference in references:
        if reference.ref_kind == SqlReferenceKind.DBT_REF:
            raise CompileInputError(
                f"Audit file {audit_file.relative_path} may not use "
                f"__dbt_ref('{reference.ref_name}') right now"
            )
        if (
            reference.ref_kind == SqlReferenceKind.REF
            and reference.ref_name not in known_model_names
        ):
            raise CompileInputError(
                f"Audit file {audit_file.relative_path} references unknown model "
                f"'{reference.ref_name}'"
            )
        if (
            reference.ref_kind == SqlReferenceKind.SOURCE
            and reference.ref_name not in known_source_names
        ):
            raise CompileInputError(
                f"Audit file {audit_file.relative_path} references unknown source "
                f"'{reference.ref_name}'"
            )


def resolve_environment_name(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    selected_environment: str | None,
) -> str | None:
    """Resolve the effective environment name for compile input building."""

    environment_name: str | None = selected_environment
    if environment_name is None:
        environment_name = local_config.environment
    if environment_name is None:
        environment_name = project_config.default_environment
    if environment_name is None:
        return None
    if (
        environment_name not in project_config.environments
        and environment_name not in local_config.environments
    ):
        raise CompileInputError(f"Unknown environment '{environment_name}'")
    return environment_name


def resolve_environment_config(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    environment_name: str,
) -> EnvironmentConfig:
    """Merge project environment config with local developer overrides."""

    project_environment: EnvironmentConfig = project_config.environments.get(
        environment_name, EnvironmentConfig()
    )
    local_environment: LocalEnvironmentConfig | None = local_config.environments.get(
        environment_name
    )
    if local_environment is None:
        return project_environment
    return EnvironmentConfig(
        connection={**project_environment.connection, **local_environment.connection},
        vars={**project_environment.vars, **local_environment.vars},
        database=(
            local_environment.database
            if local_environment.database is not None
            else project_environment.database
        ),
        schema=(
            local_environment.schema
            if local_environment.schema is not None
            else project_environment.schema
        ),
        clone=_merge_clone_policy(
            project_clone=project_environment.clone,
            local_clone=local_environment.clone,
        ),
    )


def _merge_clone_policy(
    *, project_clone: ClonePolicy, local_clone: LocalClonePolicy
) -> ClonePolicy:
    allow_as_source: bool | None = local_clone.allow_as_source
    allow_as_target: bool | None = local_clone.allow_as_target
    return ClonePolicy(
        allow_as_source=(
            allow_as_source if allow_as_source is not None else project_clone.allow_as_source
        ),
        allow_as_target=(
            allow_as_target if allow_as_target is not None else project_clone.allow_as_target
        ),
    )


def build_effective_connection(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    environment_config: EnvironmentConfig | None,
    effective_vars: dict[str, str],
) -> dict[str, object]:
    """Merge base project connection with the selected environment overrides."""

    connection: dict[str, object] = dict(project_config.connection)
    if environment_config is not None:
        connection.update(environment_config.connection)
    connection.update(local_config.connection)
    return cast(
        dict[str, object],
        expand_template_data(
            connection,
            variables=effective_vars,
            context_values={},
            context_label="effective connection",
            allow_context=False,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        ),
    )


def build_effective_settings(
    *, project_config: ProjectConfig, local_config: LocalConfig
) -> SettingsConfig:
    """Merge project settings with local developer overrides."""

    values: dict[str, object] = {
        field.name: getattr(project_config.settings, field.name) for field in fields(SettingsConfig)
    }
    setting_name: str
    for setting_name in local_config.setting_overrides:
        values[setting_name] = getattr(local_config.settings, setting_name)
    return SettingsConfig(**cast(dict[str, Any], values))


def build_known_ref_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __ref() targets (models + seeds)."""

    return {
        discovered_model_file.file_path.stem
        for discovered_model_file in discovered_inputs.model_files
    } | {
        seed_entry.name
        for schema_file in discovered_inputs.schema_files
        for seed_entry in schema_file.seed_entries
    }


def build_known_source_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __source() targets."""

    return {
        source_entry.name
        for source_file in discovered_inputs.source_files
        for source_entry in source_file.source_entries
    }


def build_known_function_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of names valid as __udf() targets."""

    return {
        *(function_file.file_path.stem for function_file in discovered_inputs.sql_function_files),
        *(
            function_file.file_path.stem
            for function_file in discovered_inputs.python_function_files
        ),
    }


def build_known_table_function_names(discovered_inputs: DiscoveredProjectInputs) -> set[str]:
    """Build the set of discovered SQL functions declared as table functions."""

    return {
        function_file.file_path.stem
        for function_file in discovered_inputs.sql_function_files
        if _is_table_function_returns(function_file.header_values.get("returns"))
    }


def _is_table_function_returns(raw_returns: object) -> bool:
    return isinstance(raw_returns, dict) and set(raw_returns) == {"table"}


def build_effective_vars(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    environment_config: EnvironmentConfig | None,
    cli_vars: dict[str, str],
) -> dict[str, str]:
    """Merge effective vars using the locked precedence order."""

    values: dict[str, str] = dict(project_config.vars)
    if environment_config is not None:
        values.update(environment_config.vars)
    values.update(local_config.vars)
    values.update(cli_vars)
    return expand_effective_vars(values)


def build_model_config(
    *,
    defaults: DefaultsConfig,
    path_defaults: dict[str, dict[str, object]],
    matched_path_default: str | None,
    model_header_values: dict[str, object],
    effective_vars: dict[str, str],
    environment_config: EnvironmentConfig | None,
    model_name: str,
    effective_environment_name: str | None,
    run_id: str,
) -> CompileModelConfig:
    """Build the pre-semantic effective model config layers."""

    _validate_model_header_tags(model_header_values=model_header_values, model_name=model_name)
    layered_values: dict[str, object] = build_layered_model_values(
        defaults=defaults,
        path_defaults=path_defaults,
        matched_path_default=matched_path_default,
        model_header_values=model_header_values,
    )
    early_resolved_values: dict[str, object] = resolve_early_model_templates(
        values=layered_values,
        effective_vars=effective_vars,
        effective_environment_name=effective_environment_name,
        run_id=run_id,
    )
    model_resolved_values: dict[str, object] = resolve_model_context_templates(
        values=early_resolved_values,
        model_name=model_name,
        effective_environment_name=effective_environment_name,
        run_id=run_id,
    )
    model_resolved_values = resolve_model_context_templates(
        values=model_resolved_values,
        model_name=model_name,
        effective_environment_name=effective_environment_name,
        run_id=run_id,
    )
    raw_logical_schema: object | None = model_resolved_values.get("schema")
    raw_logical_database: object | None = model_resolved_values.get("database")
    logical_schema: str | None = raw_logical_schema if isinstance(raw_logical_schema, str) else None
    logical_database: str | None = (
        raw_logical_database if isinstance(raw_logical_database, str) else None
    )
    apply_environment_database_schema_overrides(
        values=model_resolved_values,
        effective_vars=effective_vars,
        environment_config=environment_config,
        model_context_values=build_model_context_values(
            values=model_resolved_values,
            model_name=model_name,
            effective_environment_name=effective_environment_name,
            run_id=run_id,
            include_target_values=False,
        ),
    )
    target_resolved_values: dict[str, object] = resolve_target_context_templates(
        values=model_resolved_values,
        model_name=model_name,
        effective_environment_name=effective_environment_name,
        run_id=run_id,
    )
    validate_model_config_has_no_macros(values=target_resolved_values)
    return CompileModelConfig(
        values=target_resolved_values,
        matched_path_default=matched_path_default,
        logical_schema=logical_schema,
        logical_database=logical_database,
    )


def expand_model_hook_macros(
    *,
    values: dict[str, object],
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    macro_context: MacroContext,
) -> dict[str, object]:
    """Expand macros only within executable hook SQL strings."""

    expanded_values: dict[str, object] = dict(values)
    hook_key: str
    for hook_key in ("pre_hook", "post_hook"):
        raw_hook_value: object | None = expanded_values.get(hook_key)
        if raw_hook_value is None:
            continue
        expanded_values[hook_key] = expand_sql_macros_in_value(
            value=raw_hook_value,
            file_path=file_path,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
        )
    return expanded_values


def expand_sql_macros_in_value(
    *,
    value: object,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    macro_context: MacroContext,
) -> object:
    """Recursively expand macros inside supported SQL hook container shapes."""

    if isinstance(value, str):
        return expand_sql_macros(
            sql=value,
            file_path=file_path,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
        )
    if isinstance(value, list):
        return [
            expand_sql_macros_in_value(
                value=item,
                file_path=file_path,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
            )
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            expand_sql_macros_in_value(
                value=item,
                file_path=file_path,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
            )
            for item in value
        )
    return value


def validate_model_config_has_no_macros(*, values: dict[str, object]) -> None:
    """Reject macro calls in declarative model config while allowing hook SQL strings."""

    validate_no_macros_in_config_value(value=values, path=())


def validate_no_macros_in_config_value(*, value: object, path: tuple[str, ...]) -> None:
    """Recursively reject macro calls outside hook fields."""

    if path and path[0] in {"pre_hook", "post_hook"}:
        return
    if isinstance(value, str):
        if MACRO_CALL_PATTERN.search(value) is not None:
            field_path: str = ".".join(path) if path else "<root>"
            raise CompileInputError(f"model config field '{field_path}' does not allow macros")
        return
    if isinstance(value, dict):
        key: object
        item_value: object
        for key, item_value in value.items():
            if isinstance(key, str):
                validate_no_macros_in_config_value(value=item_value, path=(*path, key))
        return
    if isinstance(value, list | tuple):
        item: object
        for item in value:
            validate_no_macros_in_config_value(value=item, path=path)


def build_layered_model_values(
    *,
    defaults: DefaultsConfig,
    path_defaults: dict[str, dict[str, object]],
    matched_path_default: str | None,
    model_header_values: dict[str, object],
) -> dict[str, object]:
    """Layer project defaults, path defaults, and MODEL header values."""

    values: dict[str, object] = project_defaults_to_mapping(defaults)
    if matched_path_default is not None:
        _merge_with_tag_union(values, path_defaults[matched_path_default])
    _merge_with_tag_union(values, model_header_values)
    return values


def _merge_with_tag_union(base: dict[str, object], overlay: dict[str, object]) -> None:
    """Merge overlay into base, preserving special config merge semantics."""

    overlay_tags: object | None = overlay.get("tags")
    base_tags: object | None = base.get("tags")
    overlay_row_diff_exclude_columns: object | None = overlay.get("row_diff_exclude_columns")
    base_row_diff_exclude_columns: object | None = base.get("row_diff_exclude_columns")
    overlay_row_diff_tolerances: object | None = overlay.get("row_diff_tolerances")
    base_row_diff_tolerances: object | None = base.get("row_diff_tolerances")
    base.update(overlay)
    if overlay_tags is not None and base_tags is not None:
        merged: list[str] = list(_as_string_list(base_tags))
        tag: str
        for tag in _as_string_list(overlay_tags):
            if tag not in merged:
                merged.append(tag)
        base["tags"] = merged
    if overlay_row_diff_exclude_columns is not None and base_row_diff_exclude_columns is not None:
        base["row_diff_exclude_columns"] = tuple(
            _merge_string_sequence(
                base_row_diff_exclude_columns,
                overlay_row_diff_exclude_columns,
            )
        )
    if overlay_row_diff_tolerances is not None and base_row_diff_tolerances is not None:
        base["row_diff_tolerances"] = _merge_row_diff_tolerances_mapping(
            base_row_diff_tolerances,
            overlay_row_diff_tolerances,
        )


def _merge_string_sequence(base: object, overlay: object) -> list[str]:
    """Merge string sequence-like values while preserving first occurrence order."""

    merged: list[str] = list(_as_string_list(base))
    value: str
    for value in _as_string_list(overlay):
        if value not in merged:
            merged.append(value)
    return merged


def _merge_row_diff_tolerances_mapping(base: object, overlay: object) -> object:
    """Deep merge row diff tolerance mappings by section and rule key."""

    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return overlay

    base_mapping: dict[str, object] = cast(dict[str, object], base)
    overlay_mapping: dict[str, object] = cast(dict[str, object], overlay)
    merged: dict[str, object] = dict(base_mapping)
    section: str
    for section in ("by_type", "by_column"):
        base_section: object | None = base_mapping.get(section)
        overlay_section: object | None = overlay_mapping.get(section)
        if overlay_section is None:
            continue
        if isinstance(base_section, dict) and isinstance(overlay_section, dict):
            merged[section] = {**base_section, **overlay_section}
        else:
            merged[section] = overlay_section
    key: object
    value: object
    for key, value in overlay_mapping.items():
        if isinstance(key, str) and key not in {"by_type", "by_column"}:
            merged[key] = value
    return merged


def _as_string_list(value: object) -> list[str]:
    """Coerce a tags value to a list of strings."""

    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    return []


def _validate_model_header_tags(
    *,
    model_header_values: dict[str, object],
    model_name: str,
) -> None:
    """Validate that tags in a MODEL header is a list of strings."""

    raw_tags: object | None = model_header_values.get("tags")
    if raw_tags is None:
        return
    if not isinstance(raw_tags, list):
        raise CompileInputError(f"model '{model_name}' tags must be a list")
    item: object
    for item in raw_tags:
        if not isinstance(item, str):
            raise CompileInputError(f"model '{model_name}' tags entries must be strings")


def _merge_schema_tags(
    *, config: CompileModelConfig, schema_entry: SchemaModelEntry
) -> CompileModelConfig:
    """Union schema.yml tags into model config values."""

    if not schema_entry.tags:
        return config
    merged_values: dict[str, object] = dict(config.values)
    _merge_with_tag_union(merged_values, {"tags": list(schema_entry.tags)})
    return CompileModelConfig(
        values=merged_values,
        matched_path_default=config.matched_path_default,
    )


def resolve_early_model_templates(
    *,
    values: dict[str, object],
    effective_vars: dict[str, str],
    effective_environment_name: str | None,
    run_id: str,
) -> dict[str, object]:
    """Resolve `${name}`, `${ENV:...}`, and early `run.*` model templates."""

    return cast(
        dict[str, object],
        expand_template_data(
            values,
            variables=effective_vars,
            context_values=build_run_context_values(
                effective_environment_name=effective_environment_name,
                run_id=run_id,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=True,
        ),
    )


def resolve_model_context_templates(
    *,
    values: dict[str, object],
    model_name: str,
    effective_environment_name: str | None,
    run_id: str,
) -> dict[str, object]:
    """Resolve model-bound `CTX` values once logical model identity is known."""

    return cast(
        dict[str, object],
        expand_template_data(
            values,
            variables={},
            context_values=build_model_context_values(
                values=values,
                model_name=model_name,
                effective_environment_name=effective_environment_name,
                run_id=run_id,
                include_target_values=False,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=True,
        ),
    )


def resolve_target_context_templates(
    *,
    values: dict[str, object],
    model_name: str,
    effective_environment_name: str | None,
    run_id: str,
) -> dict[str, object]:
    """Resolve late `target.*` values after environment overrides finalize naming."""

    return cast(
        dict[str, object],
        expand_template_data(
            values,
            variables={},
            context_values=build_model_context_values(
                values=values,
                model_name=model_name,
                effective_environment_name=effective_environment_name,
                run_id=run_id,
                include_target_values=True,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        ),
    )


def build_model_context_values(
    *,
    values: dict[str, object],
    model_name: str,
    effective_environment_name: str | None,
    run_id: str,
    include_target_values: bool,
) -> dict[str, str | None]:
    """Build the currently available model-scoped CTX values."""

    raw_database: object | None = values.get("database")
    raw_schema: object | None = values.get("schema")
    raw_alias: object | None = values.get("alias")
    logical_database: str | None = None if not isinstance(raw_database, str) else raw_database
    logical_schema: str | None = None if not isinstance(raw_schema, str) else raw_schema
    logical_alias: str = model_name if not isinstance(raw_alias, str) else raw_alias
    context_values: dict[str, str | None] = {
        **build_run_context_values(
            effective_environment_name=effective_environment_name,
            run_id=run_id,
        ),
        CompileContextKey.MODEL_NAME: model_name,
        CompileContextKey.MODEL_DATABASE: logical_database,
        CompileContextKey.MODEL_SCHEMA: logical_schema,
        CompileContextKey.MODEL_ALIAS: logical_alias,
    }
    if not include_target_values:
        return context_values

    target_database: str | None = logical_database
    target_schema: str | None = logical_schema
    target_table: str = logical_alias
    target_qualified: str | None = None
    if target_database is not None and target_schema is not None:
        target_qualified = f"{target_database}.{target_schema}.{target_table}"
    elif target_schema is not None:
        target_qualified = f"{target_schema}.{target_table}"
    context_values[CompileContextKey.TARGET_DATABASE] = target_database
    context_values[CompileContextKey.TARGET_SCHEMA] = target_schema
    context_values[CompileContextKey.TARGET_TABLE] = target_table
    context_values[CompileContextKey.TARGET_QUALIFIED] = target_qualified
    return context_values


def build_run_context_values(
    *, effective_environment_name: str | None, run_id: str
) -> dict[str, str | None]:
    """Build the compile-time CTX values known before resource-specific resolution."""

    return {
        CompileContextKey.RUN_ID: run_id,
        CompileContextKey.RUN_ENVIRONMENT: effective_environment_name,
    }


def apply_environment_database_schema_overrides(
    *,
    values: dict[str, object],
    effective_vars: dict[str, str],
    environment_config: EnvironmentConfig | None,
    model_context_values: dict[str, str | None],
) -> None:
    """Apply environment database/schema overrides using the logical config as CTX."""

    if environment_config is None:
        return

    if (
        environment_config.database is not None
        and environment_config.database != PRESERVE_ENVIRONMENT_VALUE
    ):
        values["database"] = expand_template_data(
            environment_config.database,
            variables=effective_vars,
            context_values=model_context_values,
            context_label="environment database",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    if (
        environment_config.schema is not None
        and environment_config.schema != PRESERVE_ENVIRONMENT_VALUE
    ):
        values["schema"] = expand_template_data(
            environment_config.schema,
            variables=effective_vars,
            context_values=model_context_values,
            context_label="environment schema",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )


def resolve_run_id(*, selected_run_id: str | None) -> str:
    """Resolve a stable compile invocation id."""

    if selected_run_id is not None:
        return selected_run_id
    timestamp_prefix: str = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    unique_suffix: str = uuid4().hex[:6]
    return f"{timestamp_prefix}_{unique_suffix}"


def find_matching_path_default(
    *,
    model_file: DiscoveredSqlModelFile,
    path_defaults: dict[str, dict[str, object]],
) -> str | None:
    """Return the nearest matching path_defaults key for a model file."""

    relative_path: Path = Path(str(model_file.relative_path).removeprefix("models/"))
    best_match: str | None = None
    best_length: int = -1

    path_key: str
    for path_key in path_defaults:
        path_key_parts: tuple[str, ...] = Path(path_key).parts
        if relative_path.parts[: len(path_key_parts)] != path_key_parts:
            continue
        if len(path_key_parts) > best_length:
            best_match = path_key
            best_length = len(path_key_parts)
    return best_match


def project_defaults_to_mapping(defaults: DefaultsConfig) -> dict[str, object]:
    """Convert project defaults into a sparse mapping for pre-semantic overlay."""

    values: dict[str, object] = {}
    if defaults.materialized is not None:
        values["materialized"] = defaults.materialized
    if defaults.database is not None:
        values["database"] = defaults.database
    if defaults.schema is not None:
        values["schema"] = defaults.schema
    if defaults.incremental_strategy is not None:
        values["incremental_strategy"] = defaults.incremental_strategy
    if defaults.incremental_mode is not None:
        values["incremental_mode"] = defaults.incremental_mode
    if defaults.append_cursor_inclusive is not None:
        values["append_cursor_inclusive"] = defaults.append_cursor_inclusive
    if defaults.cursor_start is not None:
        values["cursor_start"] = defaults.cursor_start
    if defaults.lookback is not None:
        values["lookback"] = defaults.lookback
    if defaults.batch_size is not None:
        values["batch_size"] = defaults.batch_size
    if defaults.query_change_backfill is not None:
        values["query_change_backfill"] = defaults.query_change_backfill
    if defaults.schema_change_backfill:
        values["schema_change_backfill"] = defaults.schema_change_backfill
    if defaults.row_diff_exclude_columns:
        values["row_diff_exclude_columns"] = defaults.row_diff_exclude_columns
    if defaults.row_diff_tolerances:
        values["row_diff_tolerances"] = defaults.row_diff_tolerances
    if defaults.tags:
        values["tags"] = list(defaults.tags)
    return values


def find_schema_model_match(
    *,
    model_file: DiscoveredSqlModelFile,
    schema_files: tuple[DiscoveredSchemaFile, ...],
) -> tuple[SchemaModelEntry, DiscoveredSchemaFile] | None:
    """Find the schema.yml model entry that applies to a discovered model file."""

    model_name: str = model_file.file_path.stem
    matching_entries: list[tuple[SchemaModelEntry, DiscoveredSchemaFile]] = []
    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        schema_directory: Path = schema_file.relative_path.parent
        try:
            model_file.relative_path.relative_to(schema_directory)
        except ValueError:
            continue

        schema_entry: SchemaModelEntry
        for schema_entry in schema_file.model_entries:
            if schema_entry.name == model_name:
                matching_entries.append((schema_entry, schema_file))

    if not matching_entries:
        return None
    if len(matching_entries) > 1:
        matching_paths: str = ", ".join(
            str(schema_file.relative_path) for _, schema_file in matching_entries
        )
        raise CompileInputError(
            f"Model file {model_file.relative_path} matched multiple schema.yml declarations: "
            f"{matching_paths}"
        )
    return matching_entries[0]


def validate_declared_schema_models_are_attached(
    *,
    model_inputs: tuple[CompileModelInput, ...],
    schema_files: tuple[DiscoveredSchemaFile, ...],
) -> None:
    """Ensure every declared schema.yml model entry attaches within its directory scope."""

    attached_model_names: set[str] = {
        model_input.schema_entry.name
        for model_input in model_inputs
        if model_input.schema_entry is not None
    }
    schema_file: DiscoveredSchemaFile
    for schema_file in schema_files:
        schema_entry: SchemaModelEntry
        for schema_entry in schema_file.model_entries:
            if schema_entry.name not in attached_model_names:
                raise CompileInputError(
                    f"schema.yml declaration for model '{schema_entry.name}' in "
                    f"{schema_file.relative_path} "
                    "does not match any discovered model file in that directory scope"
                )


def resolve_audit_severity(
    *,
    instance_severity: str | None,
    default_severity: str | None,
    audit_label: str,
) -> str:
    """Resolve effective audit severity from instance, then project default."""

    from sqlbuild.compiler.auditing.types import AuditSeverity

    valid_values: frozenset[str] = frozenset(s.value for s in AuditSeverity)
    if instance_severity is not None:
        if instance_severity not in valid_values:
            raise CompileInputError(
                f"{audit_label}: unknown severity '{instance_severity}'; "
                f"valid values: {', '.join(sorted(valid_values))}"
            )
        return instance_severity
    if default_severity is not None:
        if default_severity not in valid_values:
            raise CompileInputError(
                f"settings.default_audit_severity in sqlbuild_project.yml: "
                f"unknown value '{default_severity}'; "
                f"valid values: {', '.join(sorted(valid_values))}"
            )
        return default_severity
    raise CompileInputError(
        f"{audit_label}: severity is required; set it on the audit instance "
        f"or set settings.default_audit_severity in sqlbuild_project.yml"
    )


def resolve_audit_run_scope(
    *,
    instance_run_scope: str | None,
    default_run_scope: str | None,
) -> str:
    """Resolve audit run scope from instance, project default, or delta/final fallback."""

    from sqlbuild.compiler.auditing.types import AuditRunScope

    valid_values: frozenset[str] = frozenset(s.value for s in AuditRunScope)
    if instance_run_scope is not None:
        if instance_run_scope not in valid_values:
            raise CompileInputError(
                f"unknown audit run_scope '{instance_run_scope}'; "
                f"valid values: {', '.join(sorted(valid_values))}"
            )
        return instance_run_scope
    if default_run_scope is not None:
        if default_run_scope not in valid_values:
            raise CompileInputError(
                f"settings.default_audit_run_scope in sqlbuild_project.yml: "
                f"unknown value '{default_run_scope}'; "
                f"valid values: {', '.join(sorted(valid_values))}"
            )
        return default_run_scope
    return AuditRunScope.DELTA_AND_FINAL


def validate_model_attached_audit_references(
    *,
    references: tuple[CompileSqlReference, ...],
    attached_target_kind: str,
    attached_target_name: str,
    audit_label: str,
) -> None:
    """Validate that a model-attached generic audit references the attached model."""

    if attached_target_kind != AttachedAuditTargetKind.MODEL:
        return
    ref_names: frozenset[str] = frozenset(
        ref.ref_name for ref in references if ref.ref_kind == SqlReferenceKind.REF
    )
    if attached_target_name not in ref_names:
        raise CompileInputError(
            f"{audit_label}: model-attached audit must reference the attached model "
            f"'{attached_target_name}' via __ref()"
        )


def _str_from_dict(values: dict[str, object], key: str) -> str | None:
    """Extract a string value from a dict."""

    raw: object | None = values.get(key)
    return raw if isinstance(raw, str) else None


def _is_sql_validation_enabled(*, project_setting: bool, model_config: CompileModelConfig) -> bool:
    """Resolve whether SQL validation is active for a model.

    Per-model override in MODEL header takes precedence over project setting.
    """

    raw: object | None = model_config.values.get("sql_validation")
    if isinstance(raw, bool):
        return raw
    return project_setting
