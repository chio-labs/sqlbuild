"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.attachments.constants import (
    HEADER_ARGUMENTS_STAGE,
    HEADER_METADATA_STAGE,
    HEADER_PYTHON_VALUES_STAGE,
    HEADER_RETURNS_STAGE,
    HEADER_START_STAGE,
)
from sqlbuild.compiler.attachments.main._parse_native_function_header import (
    parse_native_function_header,
)
from sqlbuild.compiler.attachments.main._resolve_native_function_namespace import (
    resolve_native_function_namespace,
)
from sqlbuild.compiler.attachments.models import (
    NativeFunctionHeader,
    NativeFunctionNamespace,
    NativeFunctionNamespaceInputs,
)
from sqlbuild.compiler.compile._helpers.analysis.compact import infer_columns_with_sql_analysis
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
from sqlbuild.compiler.compile._helpers.config.namespace_validation import (
    validate_preserved_logical_namespace,
)
from sqlbuild.compiler.compile._helpers.explicit_references.macro_arguments import (
    merge_call_site_references,
)
from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile._helpers.render.context_templates import expand_config_templates
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import reject_cursor_intrinsics
from sqlbuild.compiler.compile._helpers.render.declarations import resolve_declaration_expansion
from sqlbuild.compiler.compile._helpers.render.sql_vars import expand_authored_sql_result
from sqlbuild.compiler.compile.constants import (
    PRESERVE_TARGET_VALUE,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    AuthoredSqlExpansionResult,
    CompileSqlFunctionInput,
    CompileSqlReference,
    DeclarationExpansionContext,
    FunctionArgument,
    FunctionReturnColumn,
    InferredColumn,
    LoadedMacro,
    MacroContext,
    SqlReferenceOrigin,
)
from sqlbuild.compiler.compile.types import (
    FunctionLanguage,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredPythonFunctionFile,
    DiscoveredSqlFunctionFile,
)
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.scopes.models import ResourceIdentity
from sqlbuild.compiler.scopes.types import ResourceKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
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
    logical_database: str | None
    logical_schema: str | None
    target_database: str | None
    target_schema: str | None
    target_config: TargetConfig | None
    python_functions_inherit_default_namespace: bool


def build_sql_function_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    effective_vars: dict[str, object],
    effective_settings: SettingsConfig,
    target_config: TargetConfig | None,
    macro_context: MacroContext,
    loaded_macros: dict[str, LoadedMacro],
    declaration_expansion: DeclarationExpansionContext,
    sql_lexical_syntax: SqlLexicalSyntax,
    no_sql_validation: bool = False,
    python_functions_inherit_default_namespace: bool = True,
) -> tuple[CompileSqlFunctionInput, ...]:
    """Attach and validate SQL function metadata."""

    adapter_name: str = macro_context.adapter_name
    known_model_names: set[str] = build_known_ref_names(discovered_inputs)
    known_seed_names: set[str] = build_known_seed_names(discovered_inputs)
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    known_function_names: set[str] = build_known_function_names(discovered_inputs)
    known_table_function_names: set[str] = build_known_table_function_names(discovered_inputs)
    logical_database, logical_schema = _resolve_function_logical_namespace(
        defaults=discovered_inputs.project_config.defaults,
        effective_vars=effective_vars,
    )
    target_database, target_schema = _resolve_function_target_overrides(
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
        native_header: NativeFunctionHeader
        arguments: tuple[FunctionArgument, ...]
        returns: str
        return_columns: tuple[FunctionReturnColumn, ...]
        native_header, arguments, returns, return_columns = _sql_function_header(
            function_file=function_file, effective_vars=effective_vars
        )
        raw_database: object | None = header_values.get("database")
        raw_schema: object | None = header_values.get("schema")
        function_logical_database: str | None = (
            _expand_function_header_value(
                raw_value=raw_database,
                effective_vars=effective_vars,
                context_label=f"SQL function {function_file.relative_path} database",
            )
            if isinstance(raw_database, str)
            else logical_database
        )
        function_logical_schema: str | None = (
            _expand_function_header_value(
                raw_value=raw_schema,
                effective_vars=effective_vars,
                context_label=f"SQL function {function_file.relative_path} schema",
            )
            if isinstance(raw_schema, str)
            else logical_schema
        )
        validate_preserved_logical_namespace(
            resource_label=f"SQL function '{function_name}'",
            logical_database=function_logical_database,
            logical_schema=function_logical_schema,
            target_config=target_config,
        )
        function_database, function_schema = _sql_function_namespace(
            header_database=function_logical_database if isinstance(raw_database, str) else None,
            header_schema=function_logical_schema if isinstance(raw_schema, str) else None,
            defaults=(logical_database, logical_schema),
            targets=(target_database, target_schema),
        )
        scoped_declarations: DeclarationExpansionContext = resolve_declaration_expansion(
            context=declaration_expansion,
            file_path=function_file.file_path,
            resource=ResourceIdentity(ResourceKind.FUNCTION, function_name),
        )
        expansion: AuthoredSqlExpansionResult = expand_authored_sql_result(
            sql=function_file.body_sql,
            file_path=function_file.file_path,
            effective_vars=effective_vars,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
            declarations=scoped_declarations.declarations,
            declaration_resolver=scoped_declarations.resolver,
            value_renderer=scoped_declarations.value_renderer,
            collection_rendering=scoped_declarations.collection_rendering,
        )
        expanded_body_sql: str = expansion.sql
        reject_cursor_intrinsics(
            sql=expanded_body_sql,
            context=f"SQL function '{function_name}'",
        )
        if effective_settings.sql_analysis and not no_sql_validation:
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
        references: tuple[CompileSqlReference, ...] = merge_call_site_references(
            references=extract_sql_references(
                sql=expanded_body_sql,
                syntax=sql_lexical_syntax,
                origin=SqlReferenceOrigin(
                    file_path=function_file.file_path,
                    relative_path=function_file.relative_path,
                    contents=function_file.contents,
                ),
            ),
            argument_references=expansion.argument_references,
        )
        validate_function_references(
            references=references,
            function_file=function_file,
            known_model_names=known_model_names,
            known_seed_names=known_seed_names,
            known_source_names=known_source_names,
            known_function_names=known_function_names,
            known_table_function_names=known_table_function_names,
        )
        _raise_header_failure(header=native_header, stage=HEADER_METADATA_STAGE)
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
                logical_database=function_logical_database,
                logical_schema=function_logical_schema,
                fingerprint_database=function_database,
                fingerprint_schema=function_schema,
                fingerprint_logical_database=function_logical_database,
                fingerprint_logical_schema=function_logical_schema,
                tags=native_header.tags,
                description=native_header.description,
                declaration_usages=expansion.usages,
            )
        )
    python_context: _PythonFunctionBuildContext = _PythonFunctionBuildContext(
        effective_vars=effective_vars,
        effective_settings=effective_settings,
        adapter_name=adapter_name,
        no_sql_validation=no_sql_validation,
        logical_database=logical_database,
        logical_schema=logical_schema,
        target_database=target_database,
        target_schema=target_schema,
        target_config=target_config,
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


def _sql_function_header(
    *, function_file: DiscoveredSqlFunctionFile, effective_vars: dict[str, object]
) -> tuple[
    NativeFunctionHeader, tuple[FunctionArgument, ...], str, tuple[FunctionReturnColumn, ...]
]:
    native_header: NativeFunctionHeader = parse_native_function_header(
        header_values=function_file.header_values,
        python=False,
        relative_path=function_file.relative_path,
    )
    report_native_answer(stage=NativeStage.ATTACHMENTS, kind="function_headers")
    _raise_header_failure(header=native_header, stage=HEADER_START_STAGE)
    arguments: tuple[FunctionArgument, ...] = _expanded_native_arguments(
        header=native_header,
        label=f"SQL function {function_file.relative_path}",
        effective_vars=effective_vars,
    )
    _raise_header_failure(header=native_header, stage=HEADER_ARGUMENTS_STAGE)
    native_returns: tuple[str, tuple[FunctionReturnColumn, ...]] = _expanded_native_sql_returns(
        header=native_header,
        relative_path=function_file.relative_path,
        effective_vars=effective_vars,
    )
    _raise_header_failure(header=native_header, stage=HEADER_RETURNS_STAGE)
    return (native_header, arguments, *native_returns)


def _sql_function_namespace(
    *,
    header_database: str | None,
    header_schema: str | None,
    defaults: tuple[str | None, str | None],
    targets: tuple[str | None, str | None],
) -> tuple[str | None, str | None]:
    namespace: NativeFunctionNamespace = resolve_native_function_namespace(
        NativeFunctionNamespaceInputs(
            header_database=header_database,
            header_schema=header_schema,
            default_database=defaults[0],
            default_schema=defaults[1],
            target_database=targets[0],
            target_schema=targets[1],
            python=False,
            inherit_default_namespace=True,
        )
    )
    return namespace.database, namespace.schema


def _raise_header_failure(*, header: NativeFunctionHeader, stage: str) -> None:
    if header.failure is not None and header.failure[0] == stage:
        raise CompileInputError(header.failure[1])


def _expanded_native_arguments(
    *, header: NativeFunctionHeader, label: str, effective_vars: dict[str, object]
) -> tuple[FunctionArgument, ...]:
    return tuple(
        FunctionArgument(
            name=argument.name,
            type=_expand_function_header_value(
                raw_value=argument.type_text,
                effective_vars=effective_vars,
                context_label=f"{label} argument '{argument.raw_name}' type",
            ),
        )
        for argument in header.arguments
    )


def _expanded_native_sql_returns(
    *, header: NativeFunctionHeader, relative_path: Path, effective_vars: dict[str, object]
) -> tuple[str, tuple[FunctionReturnColumn, ...]]:
    if header.return_columns is None:
        return _expand_function_header_value(
            raw_value=cast(str, header.returns),
            effective_vars=effective_vars,
            context_label=f"SQL function {relative_path} returns",
        ), ()
    return "TABLE", tuple(
        FunctionReturnColumn(
            name=column.name,
            type=_expand_function_header_value(
                raw_value=column.type_text,
                effective_vars=effective_vars,
                context_label=(
                    f"SQL function {relative_path} return column '{column.raw_name}' type"
                ),
            ),
        )
        for column in header.return_columns
    )


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
    native_header: NativeFunctionHeader = parse_native_function_header(
        header_values=header_values,
        python=True,
        relative_path=python_function_file.relative_path,
    )
    report_native_answer(stage=NativeStage.ATTACHMENTS, kind="function_headers")
    _raise_header_failure(header=native_header, stage=HEADER_START_STAGE)
    arguments: tuple[FunctionArgument, ...] = _expanded_native_arguments(
        header=native_header,
        label=f"Python function {python_function_file.relative_path}",
        effective_vars=effective_vars,
    )
    _raise_header_failure(header=native_header, stage=HEADER_ARGUMENTS_STAGE)
    returns: str = _expand_function_header_value(
        raw_value=cast(str, native_header.returns),
        effective_vars=effective_vars,
        context_label=f"Python function {python_function_file.relative_path} returns",
    )
    _raise_header_failure(header=native_header, stage=HEADER_PYTHON_VALUES_STAGE)
    runtime_version: str = cast(str, native_header.runtime_version)
    entry_point: str = cast(str, native_header.entry_point)
    packages: tuple[str, ...] = native_header.packages
    raw_database: object | None = header_values.get("database")
    raw_schema: object | None = header_values.get("schema")
    inherit: bool = context.python_functions_inherit_default_namespace
    function_logical_database: str | None
    if isinstance(raw_database, str):
        function_logical_database = _expand_function_header_value(
            raw_value=raw_database,
            effective_vars=effective_vars,
            context_label=f"Python function {python_function_file.relative_path} database",
        )
    else:
        function_logical_database = context.logical_database if inherit else None
    function_logical_schema: str | None
    if isinstance(raw_schema, str):
        function_logical_schema = _expand_function_header_value(
            raw_value=raw_schema,
            effective_vars=effective_vars,
            context_label=f"Python function {python_function_file.relative_path} schema",
        )
    else:
        function_logical_schema = context.logical_schema if inherit else None
    namespace: NativeFunctionNamespace = resolve_native_function_namespace(
        NativeFunctionNamespaceInputs(
            header_database=function_logical_database if isinstance(raw_database, str) else None,
            header_schema=function_logical_schema if isinstance(raw_schema, str) else None,
            default_database=context.logical_database,
            default_schema=context.logical_schema,
            target_database=context.target_database,
            target_schema=context.target_schema,
            python=True,
            inherit_default_namespace=inherit,
        )
    )
    validate_preserved_logical_namespace(
        resource_label=f"Python function '{function_name}'",
        logical_database=namespace.fingerprint_logical_database,
        logical_schema=namespace.fingerprint_logical_schema,
        target_config=context.target_config,
    )
    if context.effective_settings.sql_analysis and not context.no_sql_validation:
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
    _raise_header_failure(header=native_header, stage=HEADER_METADATA_STAGE)
    return CompileSqlFunctionInput(
        function_file=python_function_file,
        name=function_name,
        arguments=arguments,
        returns=returns,
        body_sql=python_function_file.body_python,
        database=namespace.database,
        schema=namespace.schema,
        logical_database=function_logical_database,
        logical_schema=function_logical_schema,
        fingerprint_database=namespace.fingerprint_database,
        fingerprint_schema=namespace.fingerprint_schema,
        fingerprint_logical_database=namespace.fingerprint_logical_database,
        fingerprint_logical_schema=namespace.fingerprint_logical_schema,
        language=FunctionLanguage.PYTHON,
        runtime_version=runtime_version,
        entry_point=entry_point,
        packages=packages,
        tags=native_header.tags,
        description=native_header.description,
    )


def _expand_function_header_value(
    *, raw_value: str, effective_vars: dict[str, object], context_label: str
) -> str:
    return str(
        expand_config_templates(
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

    error: str | None = _native.function_type_error(type_sql, adapter_name, context)
    if error is not None:
        raise CompileInputError(error)


def _resolve_function_logical_namespace(
    *,
    defaults: DefaultsConfig,
    effective_vars: dict[str, object],
) -> tuple[str | None, str | None]:
    raw_database: str | None = (
        defaults.function_database if defaults.function_database is not None else defaults.database
    )
    database: str | None = (
        _expand_function_header_value(
            raw_value=raw_database,
            effective_vars=effective_vars,
            context_label="default function database",
        )
        if raw_database is not None
        else None
    )
    raw_schema: str | None = (
        defaults.function_schema if defaults.function_schema is not None else defaults.schema
    )
    schema: str | None = (
        _expand_function_header_value(
            raw_value=raw_schema,
            effective_vars=effective_vars,
            context_label="default function schema",
        )
        if raw_schema is not None
        else None
    )
    return database, schema


def _resolve_function_target_overrides(
    *, target_config: TargetConfig | None, effective_vars: dict[str, object]
) -> tuple[str | None, str | None]:
    if target_config is None:
        return None, None
    database: str | None = (
        _expand_function_environment_value(
            raw_value=target_config.database,
            effective_vars=effective_vars,
            context_label="target database",
        )
        if target_config.database is not None
        else None
    )
    schema: str | None = (
        _expand_function_environment_value(
            raw_value=target_config.schema,
            effective_vars=effective_vars,
            context_label="target schema",
        )
        if target_config.schema is not None
        else None
    )
    return database, schema


def _expand_function_environment_value(
    *, raw_value: str, effective_vars: dict[str, object], context_label: str
) -> str | None:
    if raw_value == PRESERVE_TARGET_VALUE:
        return None
    return str(
        expand_config_templates(
            value=raw_value,
            variables=effective_vars,
            context_values={},
            context_label=context_label,
            allow_context=False,
            preserve_context_tokens=True,
            preserve_unknown_context=False,
        )
    )
