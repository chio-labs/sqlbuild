"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from datetime import UTC, datetime
from inspect import Parameter, Signature
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from sqlbuild.compiler.auditing.main._parse_audit_instance import parse_audit_instance
from sqlbuild.compiler.compile._helpers.analysis.validation import validate_sql_syntax
from sqlbuild.compiler.compile._helpers.attachment.references import (
    build_known_function_names,
    build_known_ref_names,
    build_known_seed_names,
    build_known_source_names,
    build_known_table_function_names,
    validate_model_references,
)
from sqlbuild.compiler.compile._helpers.config.model_validation import (
    validate_contract_config,
    validate_custom_materialization_config,
    validate_incremental_config,
    validate_microbatch_project_capability,
    validate_non_incremental_config,
    validate_placeholder_config,
    validate_snapshot_config,
)
from sqlbuild.compiler.compile._helpers.refs.cache import cached_sql_reference_extractor
from sqlbuild.compiler.compile._helpers.render.arguments import render_parameterized_sql
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
    get_validated_model_cursor_intrinsics,
    reject_cursor_intrinsics,
)
from sqlbuild.compiler.compile._helpers.render.declarations import (
    build_model_declaration_indexes,
    expand_declaration_references_result,
    resolve_declaration_context,
    resolve_enum_contract_columns,
)
from sqlbuild.compiler.compile._helpers.render.macros import (
    expand_sql_macros_result,
)
from sqlbuild.compiler.compile._helpers.render.sql_vars import (
    expand_authored_sql_result,
    substitute_sql_vars,
)
from sqlbuild.compiler.compile._helpers.render.templating import (
    expand_effective_vars,
    expand_template_data,
)
from sqlbuild.compiler.compile.constants import (
    MACRO_CALL_PATTERN,
    MODEL_AUDIT_OVERRIDE_KEYS,
    MODEL_HEADER_METADATA_KEYS,
    PRESERVE_TARGET_VALUE,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    AuthoredSqlExpansionResult,
    CompileModelConfig,
    CompileModelInput,
    CompileSeedInput,
    CompileSqlReference,
    DeclarationExpansionContext,
    DeclarationExpansionResult,
    DeclarationResolutionContext,
    HookExpansionResult,
    LoadedMacro,
    MacroContext,
    MacroExpansionResult,
    ModelInputBuildContext,
)
from sqlbuild.compiler.compile.types import (
    CompileContextKey,
)
from sqlbuild.compiler.discovery.main._model_schema_columns import parse_schema_columns
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredHookFunction,
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSqlHookFile,
    DiscoveredSqlModelFile,
    EnumDeclaration,
    ModelSchemaDeclaration,
    NamedSqlHookEntry,
    PythonHookEntry,
    SqlHookEntry,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    ResourceIdentity,
    UsageRecord,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    ResourceKind,
    UsageKind,
    VisibilityReason,
)
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    LocalConfig,
    ProjectConfig,
    SchemaAuditInstance,
    SchemaColumn,
    SchemaModelEntry,
    SchemaSeedEntry,
    SettingsConfig,
    SourceLocation,
    TargetConfig,
)

_HOOK_TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{[^}]+\}")
_LEGACY_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hook", "post_hook"})
_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_HOOK_CONTEXT_PARAMETER_NAMES: frozenset[str] = frozenset(
    {"ctx", "context", "_ctx", "hook_context"}
)


@dataclass(frozen=True)
class _VisibleModelDeclarations:
    local_enums: dict[str, EnumDeclaration]
    local_constants: dict[str, ConstantDeclaration]
    enums: dict[str, EnumDeclaration]
    constants: dict[str, ConstantDeclaration]
    inaccessible_enums: dict[str, DeclarationRecord]
    inaccessible_constants: dict[str, DeclarationRecord]
    enum_visibility: dict[str, tuple[VisibilityRecord, ...]]
    constant_visibility: dict[str, tuple[VisibilityRecord, ...]]


@dataclass(frozen=True)
class _HookExpansionContext:
    file_path: Path
    effective_vars: dict[str, object]
    context_values: dict[str, str | None]
    loaded_macros: dict[str, LoadedMacro]
    macro_context: MacroContext
    declaration_expansion: DeclarationExpansionContext
    sql_hook_definitions: dict[str, DiscoveredSqlHookFile]
    consumer: ResourceIdentity
    facts: _HookExpansionFacts


@dataclass
class _HookExpansionFacts:
    usages: list[UsageRecord]

    def add(self, usages: tuple[UsageRecord, ...]) -> None:
        self.usages.extend(usages)


def build_model_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool = False,
    defer_model_sql_validation: bool = False,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    reference_cache_dir: Path | None = None,
) -> tuple[CompileModelInput, ...]:
    """Attach schema metadata to discovered model files."""

    with cached_sql_reference_extractor(root=reference_cache_dir) as extract_references:
        return _build_model_inputs(
            discovered_inputs=discovered_inputs,
            context=context,
            no_sql_validation=no_sql_validation,
            defer_model_sql_validation=defer_model_sql_validation,
            external_sql_reference_resolver=external_sql_reference_resolver,
            extract_references=extract_references,
        )


def _build_model_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool,
    defer_model_sql_validation: bool,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
    extract_references: Callable[[str], tuple[CompileSqlReference, ...]],
) -> tuple[CompileModelInput, ...]:

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
    sql_hook_definitions: dict[str, DiscoveredSqlHookFile] = _index_sql_hook_definitions(
        discovered_inputs.sql_hook_files
    )
    model_inputs: list[CompileModelInput] = []
    model_file: DiscoveredSqlModelFile
    for model_file in discovered_inputs.model_files:
        declarations: _VisibleModelDeclarations = _build_visible_declaration_indexes(
            model_file=model_file,
            context=context,
        )
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
        model_schema: ModelSchemaDeclaration | None = _resolve_model_schema(
            values=effective_config.values,
            model_name=model_file.file_path.stem,
            public_model_schemas=context.public_model_schemas,
        )
        model_schema_columns: tuple[SchemaColumn, ...] | None = (
            model_schema.columns if model_schema is not None else None
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
        model_identity: ResourceIdentity = ResourceIdentity(
            ResourceKind.MODEL, model_file.file_path.stem
        )
        declaration_expansion: DeclarationExpansionResult = expand_declaration_references_result(
            sql=var_substituted_sql,
            file_path=model_file.file_path,
            declarations=DeclarationResolutionContext(
                enums=declarations.enums,
                constants=declarations.constants,
                inaccessible_enums=declarations.inaccessible_enums,
                inaccessible_constants=declarations.inaccessible_constants,
                enum_visibility=declarations.enum_visibility,
                constant_visibility=declarations.constant_visibility,
                consumer=model_identity,
            ),
            value_renderer=context.value_renderer,
            collection_rendering=context.collection_rendering,
        )
        declaration_expanded_sql: str = declaration_expansion.sql
        macro_expansion: MacroExpansionResult = expand_sql_macros_result(
            sql=declaration_expanded_sql,
            file_path=model_file.file_path,
            loaded_macros=loaded_macros,
            macro_context=macro_context,
            declaration_resolver=context.declaration_resolver,
            consumer=model_identity,
        )
        expanded_query_sql: str = macro_expansion.sql
        expanded_query_sql = get_validated_model_cursor_intrinsics(
            sql=expanded_query_sql,
            config_values=effective_config.values,
            model_name=model_file.file_path.stem,
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
                query_sql=cursor_intrinsics_analysis_sql(
                    sql=expanded_query_sql,
                    cursor_type=effective_config.values.get("cursor_type"),
                ),
                model_name=model_file.file_path.stem,
                file_path=model_file.file_path,
                placeholders=sql_validation_placeholders,
            )
        references: tuple[CompileSqlReference, ...] = extract_references(expanded_query_sql)
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
            declared_columns=model_schema_columns,
        )
        validate_microbatch_project_capability(
            config=effective_config,
            settings=effective_settings,
            model_name=model_file.file_path.stem,
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
            declared_columns=model_schema_columns,
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
        hook_expansion: HookExpansionResult = expand_model_hook_macros_result(
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
            declaration_expansion=DeclarationExpansionContext(
                declarations=DeclarationResolutionContext(
                    enums=declarations.enums,
                    constants=declarations.constants,
                    inaccessible_enums=declarations.inaccessible_enums,
                    inaccessible_constants=declarations.inaccessible_constants,
                ),
                value_renderer=context.value_renderer,
                collection_rendering=context.collection_rendering,
                resolver=context.declaration_resolver,
            ),
            sql_hook_definitions=sql_hook_definitions,
            consumer=model_identity,
        )
        expanded_config: CompileModelConfig = CompileModelConfig(
            values=hook_expansion.values,
            matched_path_default=effective_config.matched_path_default,
            logical_schema=effective_config.logical_schema,
            logical_database=effective_config.logical_database,
        )
        hook_name: str
        for hook_name in ("pre_hooks", "post_hooks"):
            hook_value: object | None = expanded_config.values.get(hook_name)
            if isinstance(hook_value, list | tuple):
                hook_entry: object
                for hook_entry in hook_value:
                    if isinstance(hook_entry, SqlHookEntry):
                        reject_cursor_intrinsics(
                            sql=hook_entry.statement,
                            context=f"Model '{model_file.file_path.stem}' {hook_name}",
                        )
        header_schema_entry: SchemaModelEntry | None = build_model_header_schema_entry(
            model_name=model_file.file_path.stem,
            model_header_values=expanded_config.values,
            file_path=model_file.relative_path,
            column_locations=model_file.header_column_locations,
            model_schema_columns=model_schema_columns,
            model_schema_name=model_schema.name if model_schema is not None else None,
            model_schema_description=model_schema.description if model_schema is not None else None,
        )
        model_config: CompileModelConfig = strip_model_header_metadata_from_config(expanded_config)
        header_schema_entry, enum_columns = resolve_enum_contract_columns(
            schema_entry=header_schema_entry,
            config_values=model_config.values,
            enums=declarations.enums,
        )
        generated_usages: tuple[UsageRecord, ...] = _generated_enum_usages(
            enum_columns=enum_columns,
            declarations=declarations,
            consumer=model_identity,
        )
        model_declaration_usages: tuple[UsageRecord, ...] = tuple(
            dict.fromkeys(
                (*declaration_expansion.usages, *generated_usages, *hook_expansion.usages)
            )
        )
        _reject_legacy_schema_match(
            model_file=model_file, schema_files=discovered_inputs.schema_files
        )
        if header_schema_entry is None:
            model_inputs.append(
                CompileModelInput(
                    model_file=model_file,
                    config=model_config,
                    query_sql=expanded_query_sql,
                    macro_source_sql=declaration_expanded_sql,
                    references=references,
                    sql_validation_enabled=sql_validation_enabled,
                    enum_declarations=tuple(declarations.local_enums.values()),
                    constant_declarations=tuple(declarations.local_constants.values()),
                    enum_columns=enum_columns,
                    macro_deps=tuple(item.name for item in macro_expansion.dependencies),
                    macro_usages=macro_expansion.usages,
                    declaration_usages=model_declaration_usages,
                )
            )
            continue

        model_inputs.append(
            CompileModelInput(
                model_file=model_file,
                config=model_config,
                query_sql=expanded_query_sql,
                macro_source_sql=declaration_expanded_sql,
                references=references,
                schema_entry=header_schema_entry,
                sql_validation_enabled=sql_validation_enabled,
                enum_declarations=tuple(declarations.local_enums.values()),
                constant_declarations=tuple(declarations.local_constants.values()),
                enum_columns=enum_columns,
                macro_deps=tuple(item.name for item in macro_expansion.dependencies),
                macro_usages=macro_expansion.usages,
                declaration_usages=model_declaration_usages,
            )
        )

    validate_declared_schema_models_are_attached(
        model_inputs=tuple(model_inputs),
        schema_files=discovered_inputs.schema_files,
    )
    return tuple(model_inputs)


def _build_visible_declaration_indexes(
    *, model_file: DiscoveredSqlModelFile, context: ModelInputBuildContext
) -> _VisibleModelDeclarations:
    local_enums: dict[str, EnumDeclaration]
    local_constants: dict[str, ConstantDeclaration]
    model_identity: ResourceIdentity = ResourceIdentity(
        ResourceKind.MODEL, model_file.file_path.stem
    )

    local_enums, local_constants = build_model_declaration_indexes(model_file=model_file)
    visible: DeclarationResolutionContext = DeclarationResolutionContext(
        enums=context.public_enums,
        constants=context.public_constants,
    )
    if (
        context.declaration_resolver is not None
        and context.declaration_resolver.lookup.index.declarations
    ):
        visible = resolve_declaration_context(
            resolver=context.declaration_resolver, file_path=model_file.file_path
        )
    return _VisibleModelDeclarations(
        local_enums=local_enums,
        local_constants=local_constants,
        enums=visible.enums | local_enums,
        constants=visible.constants | local_constants,
        inaccessible_enums=visible.inaccessible_enums,
        inaccessible_constants=visible.inaccessible_constants,
        enum_visibility=visible.enum_visibility
        | {
            name: (
                VisibilityRecord(
                    model_identity,
                    DeclarationIdentity(DeclarationKind.ENUM, name, model_identity),
                    reason=VisibilityReason.PRIVATE_OWNER,
                ),
            )
            for name in local_enums
        },
        constant_visibility=visible.constant_visibility
        | {
            name: (
                VisibilityRecord(
                    model_identity,
                    DeclarationIdentity(DeclarationKind.CONSTANT, name, model_identity),
                    reason=VisibilityReason.PRIVATE_OWNER,
                ),
            )
            for name in local_constants
        },
    )


def _generated_enum_usages(
    *,
    enum_columns: dict[str, EnumDeclaration],
    declarations: _VisibleModelDeclarations,
    consumer: ResourceIdentity,
) -> tuple[UsageRecord, ...]:
    usages: list[UsageRecord] = []
    for enum in enum_columns.values():
        for visibility in declarations.enum_visibility.get(enum.name, ()):
            usages.append(
                UsageRecord(
                    consumer=consumer,
                    declaration=visibility.declaration,
                    kind=UsageKind.GENERATED,
                    through=visibility.through,
                )
            )
    return tuple(usages)


def _reject_legacy_schema_match(
    *, model_file: DiscoveredSqlModelFile, schema_files: tuple[DiscoveredSchemaFile, ...]
) -> None:
    schema_match: tuple[SchemaModelEntry, DiscoveredSchemaFile] | None = find_schema_model_match(
        model_file=model_file,
        schema_files=schema_files,
    )
    if schema_match is None:
        return
    schema_entry, schema_file = schema_match
    raise CompileInputError(
        f"Schema file {schema_file.relative_path} declares model '{schema_entry.name}', "
        f"but model metadata must live in {model_file.relative_path} MODEL(...). "
        "Move description, columns, and audits into the model header."
    )


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
            value=connection,
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
    declaration_expansion: DeclarationExpansionContext,
    sql_hook_definitions: dict[str, DiscoveredSqlHookFile] | None = None,
    consumer: ResourceIdentity | None = None,
) -> dict[str, object]:
    """Expand SQL interpolation and macros within executable hook SQL strings."""

    return expand_model_hook_macros_result(
        values=values,
        file_path=file_path,
        effective_vars=effective_vars,
        context_values=context_values,
        loaded_macros=loaded_macros,
        macro_context=macro_context,
        declaration_expansion=declaration_expansion,
        sql_hook_definitions=sql_hook_definitions,
        consumer=consumer,
    ).values


def expand_model_hook_macros_result(
    *,
    values: dict[str, object],
    file_path: Path,
    effective_vars: dict[str, object],
    context_values: dict[str, str | None],
    loaded_macros: dict[str, LoadedMacro],
    macro_context: MacroContext,
    declaration_expansion: DeclarationExpansionContext,
    sql_hook_definitions: dict[str, DiscoveredSqlHookFile] | None = None,
    consumer: ResourceIdentity | None = None,
) -> HookExpansionResult:
    """Expand hooks and retain declaration usages from inline and named SQL."""

    expanded_values: dict[str, object] = dict(values)
    facts: _HookExpansionFacts = _HookExpansionFacts(usages=[])
    hook_key: str
    for hook_key in _MODEL_HOOK_KEYS:
        raw_hook_value: object | None = expanded_values.get(hook_key)
        if raw_hook_value is None:
            continue
        expanded_values[hook_key] = expand_sql_macros_in_value(
            value=raw_hook_value,
            context=_HookExpansionContext(
                file_path=file_path,
                effective_vars=effective_vars,
                context_values=context_values,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
                declaration_expansion=declaration_expansion,
                sql_hook_definitions=sql_hook_definitions or {},
                consumer=consumer or ResourceIdentity(ResourceKind.MODEL, file_path.stem),
                facts=facts,
            ),
            hook_key=hook_key,
        )
    return HookExpansionResult(values=expanded_values, usages=tuple(dict.fromkeys(facts.usages)))


def validate_model_hook_config(*, values: dict[str, object], model_name: str) -> None:
    legacy_key: str
    for legacy_key in sorted(_LEGACY_MODEL_HOOK_KEYS):
        if legacy_key in values:
            plural_key: str = f"{legacy_key}s"
            raise CompileInputError(
                f"model '{model_name}' uses legacy '{legacy_key}'; use typed '{plural_key}' "
                'entries like inline_sql("..."), sql("hook_name"), or '
                'python("hook_name")'
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
            if isinstance(hook_entry, SqlHookEntry | NamedSqlHookEntry | PythonHookEntry):
                continue
            raise CompileInputError(
                f"model '{model_name}' {hook_key} entries must use typed inline_sql(...), "
                "sql(...), or python(...) hook syntax"
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
    context: _HookExpansionContext,
    hook_key: str | None = None,
    hook_index: int | None = None,
) -> object:
    """Recursively expand SQL interpolation and macros in hook container shapes."""

    if isinstance(value, str):
        if _HOOK_TEMPLATE_PATTERN.search(value) is not None:
            hook_label: str = _format_sql_hook_label(hook_key=hook_key, hook_index=hook_index)
            raise CompileInputError(
                f"{hook_label} in '{context.file_path}' uses unsupported ${{...}} template syntax. "
                "Use @@CTX:..., @@ENV:..., or @@project_var inside SQL hooks."
            )
        declaration_context: DeclarationResolutionContext = (
            context.declaration_expansion.declarations
        )
        if context.declaration_expansion.resolver is not None:
            declaration_context = resolve_declaration_context(
                resolver=context.declaration_expansion.resolver,
                file_path=context.file_path,
            )
        expansion: AuthoredSqlExpansionResult = expand_authored_sql_result(
            sql=value,
            file_path=context.file_path,
            effective_vars=context.effective_vars,
            context_values=context.context_values,
            loaded_macros=context.loaded_macros,
            macro_context=context.macro_context,
            declaration_resolver=context.declaration_expansion.resolver,
            value_renderer=context.declaration_expansion.value_renderer,
            collection_rendering=context.declaration_expansion.collection_rendering,
            declarations=replace(declaration_context, consumer=context.consumer),
        )
        facts: _HookExpansionFacts = context.facts
        facts.add(expansion.usages)
        return expansion.sql
    if isinstance(value, SqlHookEntry):
        expanded_statement: object = expand_sql_macros_in_value(
            value=value.statement,
            context=context,
            hook_key=hook_key,
            hook_index=hook_index,
        )
        expanded_statement_text: str = str(expanded_statement)
        _require_nonempty_sql_hook_payload(
            statement=expanded_statement_text,
            hook_label=_format_sql_hook_label(hook_key=hook_key, hook_index=hook_index),
            file_path=context.file_path,
        )
        return SqlHookEntry(
            statement=expanded_statement_text,
            name=value.name,
            relative_path=value.relative_path,
            definition_sql=value.definition_sql,
            kwargs=value.kwargs,
            description=value.description,
        )
    if isinstance(value, NamedSqlHookEntry):
        hook_definition: DiscoveredSqlHookFile | None = context.sql_hook_definitions.get(value.name)
        if hook_definition is None:
            known_hook_names: str = (
                ", ".join(sorted(context.sql_hook_definitions)) or "none discovered"
            )
            hook_label = _format_named_sql_hook_label(
                hook_name=value.name,
                hook_key=hook_key,
                hook_index=hook_index,
            )
            raise CompileInputError(
                f"{hook_label} in '{context.file_path}' references an unknown SQL hook. "
                f"Discovered SQL hooks: {known_hook_names}. If this is an inline SQL "
                'statement, use inline_sql("...").'
            )
        rendered_statement: str = render_parameterized_sql(
            sql=hook_definition.sql_body,
            arguments=value.kwargs,
            owner_label=(
                f"{context.file_path} "
                + _format_named_sql_hook_label(
                    hook_name=value.name,
                    hook_key=hook_key,
                    hook_index=hook_index,
                )
            ),
            definition_label=(f"SQL hook '{value.name}' in {hook_definition.relative_path}"),
            reject_unused=True,
        )
        expanded_statement = expand_sql_macros_in_value(
            value=rendered_statement,
            context=replace(
                context,
                file_path=hook_definition.file_path,
                consumer=ResourceIdentity(ResourceKind.HOOK, value.name),
            ),
            hook_key=hook_key,
            hook_index=hook_index,
        )
        expanded_statement_text: str = str(expanded_statement)
        _require_nonempty_sql_hook_payload(
            statement=expanded_statement_text,
            hook_label=_format_named_sql_hook_label(
                hook_name=value.name,
                hook_key=hook_key,
                hook_index=hook_index,
            ),
            file_path=context.file_path,
        )
        return SqlHookEntry(
            statement=expanded_statement_text,
            name=value.name,
            relative_path=hook_definition.relative_path,
            definition_sql=hook_definition.sql_body,
            kwargs=dict(value.kwargs),
            description=hook_definition.description,
        )
    if isinstance(value, PythonHookEntry):
        return value
    if isinstance(value, list):
        return [
            expand_sql_macros_in_value(
                value=item,
                context=context,
                hook_key=hook_key,
                hook_index=index,
            )
            for index, item in enumerate(value)
        ]
    if isinstance(value, tuple):
        return tuple(
            expand_sql_macros_in_value(
                value=item,
                context=context,
                hook_key=hook_key,
                hook_index=index,
            )
            for index, item in enumerate(value)
        )
    return value


def _format_sql_hook_label(*, hook_key: str | None, hook_index: int | None) -> str:
    if hook_key is None:
        return 'inline_sql("...") hook'
    if hook_index is None:
        return f'{hook_key} inline_sql("...")'
    return f'{hook_key}[{hook_index}] inline_sql("...")'


def _format_named_sql_hook_label(
    *, hook_name: str, hook_key: str | None, hook_index: int | None
) -> str:
    if hook_key is None:
        return f'sql("{hook_name}") hook'
    if hook_index is None:
        return f'{hook_key} sql("{hook_name}")'
    return f'{hook_key}[{hook_index}] sql("{hook_name}")'


def _require_nonempty_sql_hook_payload(*, statement: str, hook_label: str, file_path: Path) -> None:
    if not statement.strip():
        raise CompileInputError(
            f"{hook_label} in '{file_path}' must render a non-empty SQL payload"
        )


def _index_sql_hook_definitions(
    hook_files: tuple[DiscoveredSqlHookFile, ...],
) -> dict[str, DiscoveredSqlHookFile]:
    definitions: dict[str, DiscoveredSqlHookFile] = {}
    hook_file: DiscoveredSqlHookFile
    for hook_file in hook_files:
        existing: DiscoveredSqlHookFile | None = definitions.get(hook_file.name)
        if existing is not None:
            raise CompileInputError(
                f"Duplicate SQL hook name '{hook_file.name}' found in "
                f"{existing.relative_path} and {hook_file.relative_path}"
            )
        definitions[hook_file.name] = hook_file
    return definitions


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
        values = _merged_with_tag_union(base=values, overlay=path_defaults[matched_path_default])
    return _merged_with_tag_union(base=values, overlay=model_header_values)


def _merged_with_tag_union(
    *, base: dict[str, object], overlay: dict[str, object]
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
                base=base_row_diff_exclude_columns,
                overlay=overlay_row_diff_exclude_columns,
            )
        )
    if overlay_row_diff_tolerances is not None and base_row_diff_tolerances is not None:
        result["row_diff_tolerances"] = _merge_row_diff_tolerances_mapping(
            base=base_row_diff_tolerances,
            overlay=overlay_row_diff_tolerances,
        )
    return result


def _merge_string_sequence(*, base: object, overlay: object) -> list[str]:
    """Merge string sequence-like values while preserving first occurrence order."""

    merged: list[str] = list(_as_string_list(base))
    value: str
    for value in _as_string_list(overlay):
        if value not in merged:
            merged.append(value)
    return merged


def _merge_row_diff_tolerances_mapping(*, base: object, overlay: object) -> object:
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
        if isinstance(key, str) and key not in MODEL_AUDIT_OVERRIDE_KEYS:
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
    model_schema_columns: tuple[SchemaColumn, ...] | None = None,
    model_schema_name: str | None = None,
    model_schema_description: str | None = None,
) -> SchemaModelEntry | None:
    """Normalize model-owned MODEL(...) metadata into the existing schema entry shape."""

    raw_description: object | None = model_header_values.get("description")
    raw_columns: object | None = model_header_values.get("columns")
    raw_audits: object | None = model_header_values.get("audits")
    if (
        raw_description is None
        and raw_columns is None
        and raw_audits is None
        and model_schema_columns is None
    ):
        return None

    model_description: str | None = _optional_model_header_string(
        raw_value=raw_description,
        file_path=file_path,
        label="model",
        key="description",
    )
    description: str | None = model_description or model_schema_description
    local_columns: tuple[SchemaColumn, ...] = _parse_model_header_columns(
        raw_columns=raw_columns,
        file_path=file_path,
        column_locations=column_locations or {},
    )
    columns: tuple[SchemaColumn, ...] = _merge_model_schema_columns(
        model_name=model_name,
        file_path=file_path,
        model_schema_columns=model_schema_columns,
        local_columns=local_columns,
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
        model_schema=model_schema_name,
        description=description,
        type_enforcement=type_enforcement,
        columns=columns,
        audits=audits,
    )


def strip_model_header_metadata_from_config(config: CompileModelConfig) -> CompileModelConfig:
    """Remove model metadata keys after they have been attached as schema metadata."""

    filtered_values: dict[str, object] = {
        key: value for key, value in config.values.items() if key not in MODEL_HEADER_METADATA_KEYS
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
    return parse_schema_columns(
        raw_columns=raw_columns,
        file_path=file_path,
        label="model",
        error_class=CompileInputError,
        column_locations=column_locations,
    )


def _merge_model_schema_columns(
    *,
    model_name: str,
    file_path: Path,
    model_schema_columns: tuple[SchemaColumn, ...] | None,
    local_columns: tuple[SchemaColumn, ...],
) -> tuple[SchemaColumn, ...]:
    if model_schema_columns is None:
        return local_columns
    merged_named_columns: list[SchemaColumn] = list(model_schema_columns)
    named_index_by_name: dict[str, int] = {
        column.name.lower(): index for index, column in enumerate(model_schema_columns)
    }
    additional_columns: list[SchemaColumn] = []
    local_column: SchemaColumn
    for local_column in local_columns:
        named_index: int | None = named_index_by_name.get(local_column.name.lower())
        if named_index is None:
            additional_columns.append(local_column)
            continue
        named_column: SchemaColumn = merged_named_columns[named_index]
        _validate_model_schema_audit_augmentation(
            model_name=model_name,
            file_path=file_path,
            local_column=local_column,
            named_column=named_column,
        )
        merged_named_columns[named_index] = replace(
            named_column,
            audits=_merge_schema_audits(
                inherited_audits=named_column.audits,
                local_audits=local_column.audits,
            ),
        )
    return (*merged_named_columns, *additional_columns)


def _merge_schema_audits(
    *,
    inherited_audits: tuple[SchemaAuditInstance, ...],
    local_audits: tuple[SchemaAuditInstance, ...],
) -> tuple[SchemaAuditInstance, ...]:
    merged_audits: list[SchemaAuditInstance] = list(inherited_audits)
    audit: SchemaAuditInstance
    for audit in local_audits:
        if audit not in merged_audits:
            merged_audits.append(audit)
    return tuple(merged_audits)


def _validate_model_schema_audit_augmentation(
    *,
    model_name: str,
    file_path: Path,
    local_column: SchemaColumn,
    named_column: SchemaColumn,
) -> None:
    named_origin: str = (
        f"{named_column.location.path}:{named_column.location.line}"
        if named_column.location is not None
        else "the named schema"
    )
    overridden_fields: list[str] = []
    if local_column.type is not None:
        overridden_fields.append("type")
    if local_column.nullable is not None:
        overridden_fields.append("nullable")
    if local_column.description is not None:
        overridden_fields.append("description")
    if overridden_fields:
        raise CompileInputError(
            f"model '{model_name}' in {file_path} cannot override "
            f"{', '.join(overridden_fields)} for named-schema column '{local_column.name}' from "
            f"{named_origin}; only audit augmentation is supported"
        )
    if not local_column.audits:
        raise CompileInputError(
            f"model '{model_name}' in {file_path} redeclares named-schema column "
            f"'{local_column.name}' from {named_origin} without audits; only audit augmentation "
            "is supported"
        )


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


def _resolve_model_schema(
    *,
    values: dict[str, object],
    model_name: str,
    public_model_schemas: dict[str, ModelSchemaDeclaration],
) -> ModelSchemaDeclaration | None:
    raw_name: object | None = values.get("model_schema")
    if raw_name is None:
        return None
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise CompileInputError(f"model '{model_name}': model_schema must be a non-empty string")
    declaration: ModelSchemaDeclaration | None = public_model_schemas.get(raw_name)
    if declaration is None:
        available: str = ", ".join(sorted(public_model_schemas)) or "none"
        raise CompileInputError(
            f"model '{model_name}' references unknown model_schema '{raw_name}'; "
            f"available schemas: {available}"
        )
    return declaration


def _merge_schema_tags(
    *, config: CompileModelConfig, schema_entry: SchemaModelEntry
) -> CompileModelConfig:
    """Union schema.yml tags into model config values."""

    if not schema_entry.tags:
        return config
    merged_values: dict[str, object] = _merged_with_tag_union(
        base=dict(config.values),
        overlay={"tags": list(schema_entry.tags)},
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
            value=values,
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
            value=values,
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
            value=values,
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
            value=target_config.database,
            variables=effective_vars,
            context_values=model_context_values,
            context_label="environment database",
            allow_context=True,
            preserve_context_tokens=False,
            preserve_unknown_context=False,
        )
    if target_config.schema is not None and target_config.schema != PRESERVE_TARGET_VALUE:
        overridden["schema"] = expand_template_data(
            value=target_config.schema,
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
    if defaults.merge_exclude_columns:
        values["merge_exclude_columns"] = defaults.merge_exclude_columns
    if defaults.allow_full_refresh is not None:
        values["allow_full_refresh"] = defaults.allow_full_refresh
    if defaults.append_cursor_inclusive is not None:
        values["append_cursor_inclusive"] = defaults.append_cursor_inclusive
    if defaults.cursor_start is not None:
        values["cursor_start"] = defaults.cursor_start
    if defaults.lookback is not None:
        values["lookback"] = defaults.lookback
    if defaults.batch_size is not None:
        values["batch_size"] = defaults.batch_size
    if defaults.batch_concurrency is not None:
        values["batch_concurrency"] = defaults.batch_concurrency
    if defaults.unaccounted_partition_policy is not None:
        values["unaccounted_partition_policy"] = defaults.unaccounted_partition_policy
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


def _str_from_dict(*, values: dict[str, object], key: str) -> str | None:
    """Extract a string value from a dict."""

    raw: object | None = values.get(key)
    return raw if isinstance(raw, str) else None


def _bool_from_dict(*, values: dict[str, object], key: str) -> bool:
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
