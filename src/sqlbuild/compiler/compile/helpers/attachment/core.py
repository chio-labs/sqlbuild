"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

import inspect
import re
from dataclasses import fields
from datetime import UTC, datetime
from inspect import Parameter, Signature
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from sqlbuild.compiler.compile.constants import (
    MACRO_CALL_PATTERN,
    PRESERVE_TARGET_VALUE,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.helpers.analysis.validation import (
    validate_hook_sql_syntax,
    validate_sql_syntax,
)
from sqlbuild.compiler.compile.helpers.attachment.references import (
    build_known_function_names,
    build_known_ref_names,
    build_known_seed_names,
    build_known_source_names,
    build_known_table_function_names,
    validate_model_references,
)
from sqlbuild.compiler.compile.helpers.config.model_validation import (
    validate_contract_config,
    validate_custom_materialization_config,
    validate_incremental_config,
    validate_non_incremental_config,
    validate_placeholder_config,
    validate_snapshot_config,
)
from sqlbuild.compiler.compile.helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.helpers.render.macros import (
    expand_sql_macros,
)
from sqlbuild.compiler.compile.helpers.render.sql_vars import (
    expand_authored_sql,
    substitute_sql_vars,
)
from sqlbuild.compiler.compile.helpers.render.templating import (
    expand_effective_vars,
    expand_template_data,
)
from sqlbuild.compiler.compile.models.core import (
    CompileModelConfig,
    CompileModelInput,
    CompileSeedInput,
    CompileSqlReference,
    LoadedMacro,
    MacroContext,
    ModelInputBuildContext,
)
from sqlbuild.compiler.compile.types import (
    CompileContextKey,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredHookFunction,
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSqlModelFile,
)
from sqlbuild.compiler.shared.helpers.schema_audits import parse_audit_instance
from sqlbuild.shared.models import PythonHookEntry, SqlHookEntry
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.spec.models.project import (
    DefaultsConfig,
    LocalConfig,
    ProjectConfig,
    SettingsConfig,
    TargetConfig,
)
from sqlbuild.spec.models.schema import (
    SchemaAuditInstance,
    SchemaColumn,
    SchemaModelEntry,
    SchemaSeedEntry,
    SourceLocation,
)

_HOOK_TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{[^}]+\}")
_LEGACY_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hook", "post_hook"})
_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_HOOK_CONTEXT_PARAMETER_NAMES: frozenset[str] = frozenset(
    {"ctx", "context", "_ctx", "hook_context"}
)


def build_model_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    context: ModelInputBuildContext,
    no_sql_validation: bool = False,
    defer_model_sql_validation: bool = False,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> tuple[CompileModelInput, ...]:
    """Attach schema metadata to discovered model files."""

    effective_vars: dict[str, object] = context.effective_vars
    effective_settings: SettingsConfig = context.effective_settings
    target_config: TargetConfig | None = context.target_config
    effective_target_name: str | None = context.effective_target_name
    run_id: str = context.run_id
    macro_context: MacroContext = context.macro_context
    loaded_macros: dict[str, LoadedMacro] = context.loaded_macros
    known_model_names: set[str] = build_known_ref_names(discovered_inputs)
    known_seed_names: set[str] = build_known_seed_names(discovered_inputs)
    known_source_names: set[str] = build_known_source_names(discovered_inputs)
    known_function_names: set[str] = build_known_function_names(discovered_inputs)
    known_table_function_names: set[str] = build_known_table_function_names(discovered_inputs)
    if external_sql_reference_resolver is not None:
        external_sql_reference_resolver.validate_model_names(known_model_names=known_model_names)
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
            target_config=target_config,
            model_name=model_file.file_path.stem,
            effective_target_name=effective_target_name,
            run_id=run_id,
        )
        validate_python_hook_config(
            values=effective_config.values,
            model_name=model_file.file_path.stem,
            hook_functions=discovered_inputs.hook_functions,
            provider_names=frozenset(provider.name for provider in discovered_inputs.providers),
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
        sql_validation_enabled: bool = _model_sql_validation_gate(
            effective_settings=effective_settings,
            no_sql_validation=no_sql_validation,
            model_config=effective_config,
        )
        if sql_validation_enabled and not defer_model_sql_validation:
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
            known_seed_names=known_seed_names,
            known_source_names=known_source_names,
            known_function_names=known_function_names,
            known_table_function_names=known_table_function_names,
            external_sql_reference_resolver=external_sql_reference_resolver,
        )
        validate_incremental_config(
            config=effective_config,
            model_name=model_file.file_path.stem,
            ref_count=len(references),
            known_input_names=frozenset(reference.ref_name for reference in references),
        )
        validate_contract_config(
            config=effective_config,
            model_name=model_file.file_path.stem,
        )
        validate_non_incremental_config(
            config=effective_config,
            model_name=model_file.file_path.stem,
        )
        validate_snapshot_config(
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
                effective_vars=effective_vars,
                context_values=build_model_context_values(
                    values=effective_config.values,
                    model_name=model_file.file_path.stem,
                    effective_target_name=effective_target_name,
                    run_id=run_id,
                    include_target_values=True,
                ),
                loaded_macros=loaded_macros,
                macro_context=macro_context,
            ),
            matched_path_default=effective_config.matched_path_default,
            logical_schema=effective_config.logical_schema,
            logical_database=effective_config.logical_database,
        )
        if sql_validation_enabled:
            hook_name: str
            for hook_name in ("pre_hooks", "post_hooks"):
                validate_hook_sql_syntax(
                    value=expanded_config.values.get(hook_name),
                    hook_name=hook_name,
                    model_name=model_file.file_path.stem,
                    file_path=model_file.file_path,
                    placeholders=sql_validation_placeholders,
                )
        header_schema_entry: SchemaModelEntry | None = build_model_header_schema_entry(
            model_name=model_file.file_path.stem,
            model_header_values=expanded_config.values,
            file_path=model_file.relative_path,
            column_locations=model_file.header_column_locations,
        )
        model_config: CompileModelConfig = strip_model_header_metadata_from_config(expanded_config)
        schema_match: tuple[SchemaModelEntry, DiscoveredSchemaFile] | None = (
            find_schema_model_match(
                model_file=model_file,
                schema_files=discovered_inputs.schema_files,
            )
        )
        if schema_match is not None:
            schema_entry: SchemaModelEntry = schema_match[0]
            schema_file: DiscoveredSchemaFile = schema_match[1]
            raise CompileInputError(
                f"Schema file {schema_file.relative_path} declares model '{schema_entry.name}', "
                f"but model metadata must live in {model_file.relative_path} MODEL(...). "
                "Move description, columns, and audits into the model header."
            )
        if header_schema_entry is None:
            model_inputs.append(
                CompileModelInput(
                    model_file=model_file,
                    config=model_config,
                    query_sql=expanded_query_sql,
                    macro_source_sql=var_substituted_sql,
                    references=references,
                    sql_validation_enabled=sql_validation_enabled,
                )
            )
            continue

        model_inputs.append(
            CompileModelInput(
                model_file=model_file,
                config=model_config,
                query_sql=expanded_query_sql,
                macro_source_sql=var_substituted_sql,
                references=references,
                schema_entry=header_schema_entry,
                sql_validation_enabled=sql_validation_enabled,
            )
        )

    validate_declared_schema_models_are_attached(
        model_inputs=tuple(model_inputs),
        schema_files=discovered_inputs.schema_files,
    )
    return tuple(model_inputs)


def build_seed_inputs(discovered_inputs: DiscoveredProjectInputs) -> tuple[CompileSeedInput, ...]:
    """Attach seed declarations to discovered seed CSV files."""

    seed_declarations: list[tuple[SchemaSeedEntry, DiscoveredSchemaFile]] = []
    schema_file: DiscoveredSchemaFile
    for schema_file in discovered_inputs.schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            seed_declarations.append((seed_entry, schema_file))

    seed_files_by_name: dict[str, DiscoveredSeedFile] = {
        seed_file.file_path.stem: seed_file for seed_file in discovered_inputs.seed_files
    }

    seed_inputs: list[CompileSeedInput] = []
    seed_entry: SchemaSeedEntry
    seed_schema_file: DiscoveredSchemaFile
    for seed_entry, seed_schema_file in seed_declarations:
        seed_file: DiscoveredSeedFile | None = seed_files_by_name.get(seed_entry.name)
        if seed_file is None:
            raise CompileInputError(
                f"Seed declaration '{seed_entry.name}' in {seed_schema_file.relative_path} "
                "has no matching CSV file under seeds/"
            )

        seed_inputs.append(
            CompileSeedInput(
                seed_file=seed_file,
                schema_entry=seed_entry,
                schema_file=seed_schema_file,
            )
        )

    return tuple(seed_inputs)


def build_effective_connection(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> dict[str, object]:
    """Merge base project connection with the selected environment overrides."""

    connection: dict[str, object] = dict(project_config.connection)
    if target_config is not None:
        connection.update(target_config.connection)
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


def build_effective_vars(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    target_config: TargetConfig | None,
    cli_vars: dict[str, object],
) -> dict[str, object]:
    """Merge effective vars using the locked precedence order."""

    values: dict[str, object] = dict(project_config.vars)
    if target_config is not None:
        values.update(target_config.vars)
    values.update(local_config.vars)
    values.update(cli_vars)
    return expand_effective_vars(values)


def build_model_config(
    *,
    defaults: DefaultsConfig,
    path_defaults: dict[str, dict[str, object]],
    matched_path_default: str | None,
    model_header_values: dict[str, object],
    effective_vars: dict[str, object],
    target_config: TargetConfig | None,
    model_name: str,
    effective_target_name: str | None,
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
    validate_model_hook_config(values=layered_values, model_name=model_name)
    raw_hook_values: dict[str, object] = {
        hook_key: layered_values[hook_key]
        for hook_key in _MODEL_HOOK_KEYS
        if hook_key in layered_values
    }
    for hook_key in raw_hook_values:
        del layered_values[hook_key]
    early_resolved_values: dict[str, object] = resolve_early_model_templates(
        values=layered_values,
        effective_vars=effective_vars,
        effective_target_name=effective_target_name,
        run_id=run_id,
    )
    model_resolved_values: dict[str, object] = _resolve_chained_model_context_templates(
        values=early_resolved_values,
        model_name=model_name,
        effective_target_name=effective_target_name,
        run_id=run_id,
    )
    raw_logical_schema: object | None = model_resolved_values.get("schema")
    raw_logical_database: object | None = model_resolved_values.get("database")
    logical_schema: str | None = raw_logical_schema if isinstance(raw_logical_schema, str) else None
    logical_database: str | None = (
        raw_logical_database if isinstance(raw_logical_database, str) else None
    )
    model_resolved_values = apply_environment_database_schema_overrides(
        values=model_resolved_values,
        effective_vars=effective_vars,
        target_config=target_config,
        model_context_values=build_model_context_values(
            values=model_resolved_values,
            model_name=model_name,
            effective_target_name=effective_target_name,
            run_id=run_id,
            include_target_values=False,
        ),
    )
    target_resolved_values: dict[str, object] = resolve_target_context_templates(
        values=model_resolved_values,
        model_name=model_name,
        effective_target_name=effective_target_name,
        run_id=run_id,
    )
    target_resolved_values.update(raw_hook_values)
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
    effective_vars: dict[str, object],
    context_values: dict[str, str | None],
    loaded_macros: dict[str, LoadedMacro],
    macro_context: MacroContext,
) -> dict[str, object]:
    """Expand SQL interpolation and macros within executable hook SQL strings."""

    expanded_values: dict[str, object] = dict(values)
    hook_key: str
    for hook_key in _MODEL_HOOK_KEYS:
        raw_hook_value: object | None = expanded_values.get(hook_key)
        if raw_hook_value is None:
            continue
        expanded_values[hook_key] = expand_sql_macros_in_value(
            value=raw_hook_value,
            file_path=file_path,
            effective_vars=effective_vars,
            context_values=context_values,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
            hook_key=hook_key,
        )
    return expanded_values


def validate_model_hook_config(*, values: dict[str, object], model_name: str) -> None:
    legacy_key: str
    for legacy_key in sorted(_LEGACY_MODEL_HOOK_KEYS):
        if legacy_key in values:
            plural_key: str = f"{legacy_key}s"
            raise CompileInputError(
                f"model '{model_name}' uses legacy '{legacy_key}'; use typed '{plural_key}' "
                'entries like sql("...") or python("hook_name")'
            )

    hook_key: str
    for hook_key in sorted(_MODEL_HOOK_KEYS):
        if hook_key not in values:
            continue
        raw_value: object = values[hook_key]
        if not isinstance(raw_value, list | tuple):
            raise CompileInputError(
                f"model '{model_name}' {hook_key} must be a list of typed hook entries"
            )
        hook_entry: object
        for hook_entry in raw_value:
            if isinstance(hook_entry, SqlHookEntry | PythonHookEntry):
                continue
            raise CompileInputError(
                f"model '{model_name}' {hook_key} entries must use typed sql(...) or "
                "python(...) hook syntax"
            )


def validate_python_hook_config(
    *,
    values: dict[str, object],
    model_name: str,
    hook_functions: tuple[DiscoveredHookFunction, ...],
    provider_names: frozenset[str] = frozenset(),
) -> None:
    """Validate Python lifecycle hook references and explicit kwargs."""

    hooks_by_name: dict[str, DiscoveredHookFunction] = {
        hook_function.name: hook_function for hook_function in hook_functions
    }
    hook_key: str
    for hook_key in sorted(_MODEL_HOOK_KEYS):
        raw_value: object | None = values.get(hook_key)
        if not isinstance(raw_value, list | tuple):
            continue
        hook_index: int
        hook_entry: object
        for hook_index, hook_entry in enumerate(raw_value):
            if not isinstance(hook_entry, PythonHookEntry):
                continue
            hook_function: DiscoveredHookFunction | None = hooks_by_name.get(hook_entry.name)
            if hook_function is None:
                known_hook_names: str = ", ".join(sorted(hooks_by_name)) or "none discovered"
                raise CompileInputError(
                    f"model '{model_name}' {hook_key}[{hook_index}] python(\"{hook_entry.name}\") "
                    f"references an unknown hook. Discovered hooks: {known_hook_names}"
                )
            validate_python_hook_signature(
                hook_entry=hook_entry,
                hook_function=hook_function,
                model_name=model_name,
                hook_key=hook_key,
                hook_index=hook_index,
                provider_names=provider_names,
            )


def validate_python_hook_signature(
    *,
    hook_entry: PythonHookEntry,
    hook_function: DiscoveredHookFunction,
    model_name: str,
    hook_key: str,
    hook_index: int,
    provider_names: frozenset[str] = frozenset(),
) -> None:
    signature: Signature = inspect.signature(hook_function.function)
    parameters: tuple[Parameter, ...] = tuple(signature.parameters.values())
    accepts_var_keyword: bool = any(
        parameter.kind is Parameter.VAR_KEYWORD for parameter in parameters
    )
    keyword_parameter_names: frozenset[str] = frozenset(
        parameter.name
        for parameter in parameters
        if parameter.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
        and parameter.name not in _HOOK_CONTEXT_PARAMETER_NAMES
    )

    context_conflicts: tuple[str, ...] = tuple(
        sorted(
            kwarg_name
            for kwarg_name in hook_entry.kwargs
            if kwarg_name in _HOOK_CONTEXT_PARAMETER_NAMES
        )
    )
    if context_conflicts:
        conflict: str = context_conflicts[0]
        raise CompileInputError(
            f"model '{model_name}' {hook_key}[{hook_index}] python(\"{hook_entry.name}\") "
            f"argument '{conflict}' conflicts with reserved context parameter '{conflict}'. "
            "Rename the hook argument; context parameters are injected by SQLBuild."
        )

    provider_conflicts: tuple[str, ...] = tuple(
        sorted(kwarg_name for kwarg_name in hook_entry.kwargs if kwarg_name in provider_names)
    )
    if provider_conflicts:
        conflict = provider_conflicts[0]
        raise CompileInputError(
            f"model '{model_name}' {hook_key}[{hook_index}] python(\"{hook_entry.name}\") "
            f"argument '{conflict}' conflicts with provider injection for parameter "
            f"'{conflict}'. Rename the hook argument or remove it to let SQLBuild inject "
            "the provider."
        )

    unknown_kwargs: tuple[str, ...] = tuple(
        sorted(
            kwarg_name
            for kwarg_name in hook_entry.kwargs
            if kwarg_name not in keyword_parameter_names and not accepts_var_keyword
        )
    )
    if unknown_kwargs:
        accepted_kwargs: str = _format_hook_parameter_names(keyword_parameter_names)
        raise CompileInputError(
            f"model '{model_name}' {hook_key}[{hook_index}] python(\"{hook_entry.name}\") "
            f"has unknown argument(s): {', '.join(unknown_kwargs)}. "
            f"Accepted configured arguments: {accepted_kwargs}"
        )

    required_positional_only: tuple[str, ...] = tuple(
        parameter.name
        for parameter in parameters
        if parameter.kind is Parameter.POSITIONAL_ONLY
        and parameter.default is Parameter.empty
        and parameter.name not in _HOOK_CONTEXT_PARAMETER_NAMES
    )
    if required_positional_only:
        raise CompileInputError(
            f"model '{model_name}' {hook_key}[{hook_index}] python(\"{hook_entry.name}\") "
            "cannot be configured because the hook function has required positional-only "
            f"parameter(s): {', '.join(required_positional_only)}. "
            "Use keyword-capable parameters for values supplied from MODEL hooks."
        )

    missing_kwargs: tuple[str, ...] = tuple(
        parameter.name
        for parameter in parameters
        if parameter.kind in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY)
        and parameter.default is Parameter.empty
        and parameter.name not in _HOOK_CONTEXT_PARAMETER_NAMES
        and parameter.name not in provider_names
        and parameter.name not in hook_entry.kwargs
    )
    if missing_kwargs:
        raise CompileInputError(
            f"model '{model_name}' {hook_key}[{hook_index}] python(\"{hook_entry.name}\") "
            f"is missing required argument(s): {', '.join(missing_kwargs)}"
        )


def _format_hook_parameter_names(parameter_names: frozenset[str]) -> str:
    if not parameter_names:
        return "none"
    return ", ".join(sorted(parameter_names))


def expand_sql_macros_in_value(
    *,
    value: object,
    file_path: Path,
    effective_vars: dict[str, object],
    context_values: dict[str, str | None],
    loaded_macros: dict[str, LoadedMacro],
    macro_context: MacroContext,
    hook_key: str | None = None,
    hook_index: int | None = None,
) -> object:
    """Recursively expand SQL interpolation and macros in hook container shapes."""

    if isinstance(value, str):
        if _HOOK_TEMPLATE_PATTERN.search(value) is not None:
            hook_label: str = _format_sql_hook_label(hook_key=hook_key, hook_index=hook_index)
            raise CompileInputError(
                f"{hook_label} in '{file_path}' uses unsupported ${{...}} template syntax. "
                "Use @@CTX:..., @@ENV:..., or @@project_var inside sql(...) hooks."
            )
        return expand_authored_sql(
            sql=value,
            file_path=file_path,
            effective_vars=effective_vars,
            context_values=context_values,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
        )
    if isinstance(value, SqlHookEntry):
        expanded_statement: object = expand_sql_macros_in_value(
            value=value.statement,
            file_path=file_path,
            effective_vars=effective_vars,
            context_values=context_values,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
            hook_key=hook_key,
            hook_index=hook_index,
        )
        return SqlHookEntry(statement=str(expanded_statement))
    if isinstance(value, PythonHookEntry):
        return value
    if isinstance(value, list):
        return [
            expand_sql_macros_in_value(
                value=item,
                file_path=file_path,
                effective_vars=effective_vars,
                context_values=context_values,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
                hook_key=hook_key,
                hook_index=index,
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, tuple):
        return tuple(
            expand_sql_macros_in_value(
                value=item,
                file_path=file_path,
                effective_vars=effective_vars,
                context_values=context_values,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
                hook_key=hook_key,
                hook_index=index,
            )
            for index, item in enumerate(value)
        )
    return value


def _format_sql_hook_label(*, hook_key: str | None, hook_index: int | None) -> str:
    if hook_key is None:
        return 'sql("...") hook'
    if hook_index is None:
        return f'{hook_key} sql("...")'
    return f'{hook_key}[{hook_index}] sql("...")'


def validate_model_config_has_no_macros(*, values: dict[str, object]) -> None:
    """Reject macro calls in declarative model config while allowing hook SQL strings."""

    validate_no_macros_in_config_value(value=values, path=())


def validate_no_macros_in_config_value(*, value: object, path: tuple[str, ...]) -> None:
    """Recursively reject macro calls outside hook fields."""

    if path and path[0] in _MODEL_HOOK_KEYS:
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
        values = _merged_with_tag_union(values, path_defaults[matched_path_default])
    return _merged_with_tag_union(values, model_header_values)


def _merged_with_tag_union(
    base: dict[str, object], overlay: dict[str, object]
) -> dict[str, object]:
    """Merge overlay into a copy of base, preserving special config merge semantics."""

    overlay_tags: object | None = overlay.get("tags")
    base_tags: object | None = base.get("tags")
    overlay_row_diff_exclude_columns: object | None = overlay.get("row_diff_exclude_columns")
    base_row_diff_exclude_columns: object | None = base.get("row_diff_exclude_columns")
    overlay_row_diff_tolerances: object | None = overlay.get("row_diff_tolerances")
    base_row_diff_tolerances: object | None = base.get("row_diff_tolerances")
    result: dict[str, object] = dict(base)
    result.update(overlay)
    if overlay_tags is not None and base_tags is not None:
        merged: list[str] = list(_as_string_list(base_tags))
        tag: str
        for tag in _as_string_list(overlay_tags):
            if tag not in merged:
                merged.append(tag)
        result["tags"] = merged
    if overlay_row_diff_exclude_columns is not None and base_row_diff_exclude_columns is not None:
        result["row_diff_exclude_columns"] = tuple(
            _merge_string_sequence(
                base_row_diff_exclude_columns,
                overlay_row_diff_exclude_columns,
            )
        )
    if overlay_row_diff_tolerances is not None and base_row_diff_tolerances is not None:
        result["row_diff_tolerances"] = _merge_row_diff_tolerances_mapping(
            base_row_diff_tolerances,
            overlay_row_diff_tolerances,
        )
    return result


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


def build_model_header_schema_entry(
    *,
    model_name: str,
    model_header_values: dict[str, object],
    file_path: Path,
    column_locations: dict[str, SourceLocation] | None = None,
) -> SchemaModelEntry | None:
    """Normalize model-owned MODEL(...) metadata into the existing schema entry shape."""

    raw_description: object | None = model_header_values.get("description")
    raw_columns: object | None = model_header_values.get("columns")
    raw_audits: object | None = model_header_values.get("audits")
    if raw_description is None and raw_columns is None and raw_audits is None:
        return None

    description: str | None = _optional_model_header_string(
        raw_value=raw_description,
        file_path=file_path,
        label="model",
        key="description",
    )
    columns: tuple[SchemaColumn, ...] = _parse_model_header_columns(
        raw_columns=raw_columns,
        file_path=file_path,
        column_locations=column_locations or {},
    )
    audits: tuple[SchemaAuditInstance, ...] = _parse_model_header_audits(
        raw_audits=raw_audits,
        file_path=file_path,
        label="model",
    )
    type_enforcement: bool | None = (
        True if any(column.type is not None for column in columns) else None
    )
    return SchemaModelEntry(
        name=model_name,
        description=description,
        type_enforcement=type_enforcement,
        columns=columns,
        audits=audits,
    )


def strip_model_header_metadata_from_config(config: CompileModelConfig) -> CompileModelConfig:
    """Remove model metadata keys after they have been attached as schema metadata."""

    filtered_values: dict[str, object] = {
        key: value
        for key, value in config.values.items()
        if key not in {"description", "columns", "audits"}
    }
    if len(filtered_values) == len(config.values):
        return config
    return CompileModelConfig(
        values=filtered_values,
        matched_path_default=config.matched_path_default,
        logical_schema=config.logical_schema,
        logical_database=config.logical_database,
    )


def _parse_model_header_columns(
    *, raw_columns: object | None, file_path: Path, column_locations: dict[str, SourceLocation]
) -> tuple[SchemaColumn, ...]:
    if raw_columns is None:
        return ()
    if not isinstance(raw_columns, dict):
        raise CompileInputError(f"{file_path} model 'columns' must be a mapping")

    parsed_columns: list[SchemaColumn] = []
    column_mapping: dict[object, object] = cast(dict[object, object], raw_columns)
    raw_column_name: object
    raw_column_metadata: object
    for raw_column_name, raw_column_metadata in column_mapping.items():
        if not isinstance(raw_column_name, str):
            raise CompileInputError(f"{file_path} model column names must be strings")
        if not raw_column_name.strip():
            raise CompileInputError(f"{file_path} model column names must be non-empty strings")
        if not isinstance(raw_column_metadata, dict):
            raise CompileInputError(
                f"{file_path} model column '{raw_column_name}' metadata must be a mapping"
            )
        column_metadata: dict[str, object] = cast(dict[str, object], raw_column_metadata)
        unknown_keys: set[str] = set(column_metadata) - {
            "type",
            "nullable",
            "description",
            "audits",
        }
        if unknown_keys:
            raise CompileInputError(
                f"{file_path} model column '{raw_column_name}' has unknown metadata keys: "
                f"{', '.join(sorted(unknown_keys))}"
            )
        nullable: bool | None = _optional_model_header_bool(
            raw_value=column_metadata.get("nullable"),
            file_path=file_path,
            label=f"model column '{raw_column_name}'",
            key="nullable",
        )
        audits: tuple[SchemaAuditInstance, ...] = _parse_model_header_audits(
            raw_audits=column_metadata.get("audits"),
            file_path=file_path,
            label=f"model column '{raw_column_name}'",
        )
        _validate_nullable_audits(
            file_path=file_path,
            column_name=raw_column_name,
            nullable=nullable,
            audit_names=tuple(audit.definition_name for audit in audits),
        )
        parsed_columns.append(
            SchemaColumn(
                name=raw_column_name,
                type=_optional_model_header_string(
                    raw_value=column_metadata.get("type"),
                    file_path=file_path,
                    label=f"model column '{raw_column_name}'",
                    key="type",
                ),
                nullable=nullable,
                description=_optional_model_header_string(
                    raw_value=column_metadata.get("description"),
                    file_path=file_path,
                    label=f"model column '{raw_column_name}'",
                    key="description",
                ),
                audits=audits,
                location=column_locations.get(raw_column_name),
            )
        )
    return tuple(parsed_columns)


def _parse_model_header_audits(
    *, raw_audits: object | None, file_path: Path, label: str
) -> tuple[SchemaAuditInstance, ...]:
    if raw_audits is None:
        return ()
    if not isinstance(raw_audits, list):
        raise CompileInputError(f"{file_path} {label} audits must be a list")
    return tuple(
        parse_audit_instance(
            raw_audit=raw_audit,
            file_path=file_path,
            label=label,
            error_class=CompileInputError,
        )
        for raw_audit in raw_audits
    )


def _optional_model_header_string(
    *, raw_value: object | None, file_path: Path, label: str, key: str
) -> str | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise CompileInputError(f"{file_path} {label} '{key}' must be a non-empty string")
    return raw_value


def _optional_model_header_bool(
    *, raw_value: object | None, file_path: Path, label: str, key: str
) -> bool | None:
    if raw_value is None:
        return None
    if not isinstance(raw_value, bool):
        raise CompileInputError(f"{file_path} {label} '{key}' must be a boolean")
    return raw_value


def _validate_nullable_audits(
    *, file_path: Path, column_name: str, nullable: bool | None, audit_names: tuple[str, ...]
) -> None:
    if nullable is True and "not_null" in audit_names:
        raise CompileInputError(
            f"{file_path} column '{column_name}' cannot set nullable = true and audit not_null",
            code="P002",
            help="remove the not_null audit or set nullable = false",
        )


def _merge_schema_tags(
    *, config: CompileModelConfig, schema_entry: SchemaModelEntry
) -> CompileModelConfig:
    """Union schema.yml tags into model config values."""

    if not schema_entry.tags:
        return config
    merged_values: dict[str, object] = _merged_with_tag_union(
        dict(config.values),
        {"tags": list(schema_entry.tags)},
    )
    return CompileModelConfig(
        values=merged_values,
        matched_path_default=config.matched_path_default,
    )


def resolve_early_model_templates(
    *,
    values: dict[str, object],
    effective_vars: dict[str, object],
    effective_target_name: str | None,
    run_id: str,
) -> dict[str, object]:
    """Resolve `${name}`, `${ENV:...}`, and early `run.*` model templates."""

    return cast(
        dict[str, object],
        expand_template_data(
            values,
            variables=effective_vars,
            context_values=build_run_context_values(
                effective_target_name=effective_target_name,
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
    effective_target_name: str | None,
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
                effective_target_name=effective_target_name,
                run_id=run_id,
                include_target_values=False,
            ),
            context_label="model config",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=True,
        ),
    )


def _resolve_chained_model_context_templates(
    *,
    values: dict[str, object],
    model_name: str,
    effective_target_name: str | None,
    run_id: str,
) -> dict[str, object]:
    """Resolve twice so ${CTX:model.*} values may chain exactly one level without looping."""

    first_pass_values: dict[str, object] = resolve_model_context_templates(
        values=values,
        model_name=model_name,
        effective_target_name=effective_target_name,
        run_id=run_id,
    )
    return resolve_model_context_templates(
        values=first_pass_values,
        model_name=model_name,
        effective_target_name=effective_target_name,
        run_id=run_id,
    )


def resolve_target_context_templates(
    *,
    values: dict[str, object],
    model_name: str,
    effective_target_name: str | None,
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
                effective_target_name=effective_target_name,
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
    effective_target_name: str | None,
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
            effective_target_name=effective_target_name,
            run_id=run_id,
        ),
        CompileContextKey.MODEL_NAME: model_name,
        CompileContextKey.MODEL_DATABASE: logical_database,
        CompileContextKey.MODEL_SCHEMA: logical_schema,
        CompileContextKey.MODEL_ALIAS: logical_alias,
    }
    if not include_target_values:
        return context_values

    destination_database: str | None = logical_database
    destination_schema: str | None = logical_schema
    destination_table: str = logical_alias
    destination_qualified: str | None = None
    if destination_database is not None and destination_schema is not None:
        destination_qualified = f"{destination_database}.{destination_schema}.{destination_table}"
    elif destination_schema is not None:
        destination_qualified = f"{destination_schema}.{destination_table}"
    context_values[CompileContextKey.DESTINATION_DATABASE] = destination_database
    context_values[CompileContextKey.DESTINATION_SCHEMA] = destination_schema
    context_values[CompileContextKey.DESTINATION_TABLE] = destination_table
    context_values[CompileContextKey.DESTINATION_QUALIFIED] = destination_qualified
    return context_values


def build_run_context_values(
    *, effective_target_name: str | None, run_id: str
) -> dict[str, str | None]:
    """Build the compile-time CTX values known before resource-specific resolution."""

    return {
        CompileContextKey.RUN_ID: run_id,
        CompileContextKey.RUN_TARGET: effective_target_name,
    }


def apply_environment_database_schema_overrides(
    *,
    values: dict[str, object],
    effective_vars: dict[str, object],
    target_config: TargetConfig | None,
    model_context_values: dict[str, str | None],
) -> dict[str, object]:
    """Return values with environment database/schema overrides applied."""

    if target_config is None:
        return dict(values)

    overridden: dict[str, object] = dict(values)
    if target_config.database is not None and target_config.database != PRESERVE_TARGET_VALUE:
        overridden["database"] = expand_template_data(
            target_config.database,
            variables=effective_vars,
            context_values=model_context_values,
            context_label="environment database",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    if target_config.schema is not None and target_config.schema != PRESERVE_TARGET_VALUE:
        overridden["schema"] = expand_template_data(
            target_config.schema,
            variables=effective_vars,
            context_values=model_context_values,
            context_label="environment schema",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    return overridden


def resolve_run_id(*, selected_run_id: str | None) -> str:
    """Resolve a stable compile invocation id."""

    if selected_run_id is not None:
        return selected_run_id
    timestamp_prefix: str = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    unique_suffix: str = uuid4().hex[:12]
    return f"{timestamp_prefix}_{unique_suffix}"


def find_matching_path_default(
    *,
    model_file: DiscoveredSqlModelFile,
    path_defaults: dict[str, dict[str, object]],
) -> str | None:
    """Return the nearest matching path_defaults key for a model file."""

    relative_path: Path = Path(
        str(model_file.relative_path).replace("\\", "/").removeprefix("models/")
    )
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
    if defaults.contract is not None:
        values["contract"] = defaults.contract
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
    if defaults.replay_on_change is not None:
        values["replay_on_change"] = defaults.replay_on_change
    if defaults.run_despite_unchanged is not None:
        values["run_despite_unchanged"] = defaults.run_despite_unchanged
    if defaults.row_diff_exclude_columns:
        values["row_diff_exclude_columns"] = defaults.row_diff_exclude_columns
    if defaults.row_diff_tolerances:
        values["row_diff_tolerances"] = defaults.row_diff_tolerances
    if defaults.tags:
        values["tags"] = list(defaults.tags)
    if defaults.pre_hooks is not None:
        values["pre_hooks"] = defaults.pre_hooks
    if defaults.post_hooks is not None:
        values["post_hooks"] = defaults.post_hooks
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


def _str_from_dict(values: dict[str, object], key: str) -> str | None:
    """Extract a string value from a dict."""

    raw: object | None = values.get(key)
    return raw if isinstance(raw, str) else None


def _bool_from_dict(values: dict[str, object], key: str) -> bool:
    raw: object | None = values.get(key)
    if raw is None:
        return False
    if not isinstance(raw, bool):
        raise CompileInputError(f"AUDIT() '{key}' must be a boolean")
    return raw


def _is_sql_validation_enabled(*, project_setting: bool, model_config: CompileModelConfig) -> bool:
    """Apply the per-model MODEL(sql_validation) override to the project setting."""

    raw: object | None = model_config.values.get("sql_validation")
    if isinstance(raw, bool):
        return raw
    return project_setting


def _model_sql_validation_gate(
    *,
    effective_settings: SettingsConfig,
    no_sql_validation: bool,
    model_config: CompileModelConfig,
) -> bool:
    """Gate validation on sql_analysis, --no-sql-validation, and project/model sql_validation."""

    return (
        effective_settings.sql_analysis
        and not no_sql_validation
        and _is_sql_validation_enabled(
            project_setting=effective_settings.sql_validation,
            model_config=model_config,
        )
    )
