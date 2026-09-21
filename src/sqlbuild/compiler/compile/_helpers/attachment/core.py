"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace
from inspect import Parameter, Signature
from pathlib import Path
from typing import Any, cast

from sqlbuild.compiler.compile._helpers.analysis.validation import validate_sql_syntax
from sqlbuild.compiler.compile._helpers.attachment.model_config import (
    _contains_model_config_macro_cached,
    _contains_template_data_cached,
    _model_sql_validation_gate,
    _resolve_model_schema,
    _validate_model_header_tags,
    build_layered_model_values,
    build_model_header_schema_entry,
    find_matching_path_default,
    find_schema_model_match,
    strip_model_header_metadata_from_config,
    validate_declared_schema_models_are_attached,
    validate_no_macros_in_config_value,
)
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
    validate_storage_policies,
)
from sqlbuild.compiler.compile._helpers.config.namespace_validation import (
    validate_preserved_logical_namespace,
)
from sqlbuild.compiler.compile._helpers.config.table_type import resolve_storage_policies
from sqlbuild.compiler.compile._helpers.refs.cache import cached_sql_reference_extractor
from sqlbuild.compiler.compile._helpers.render.arguments import render_parameterized_sql
from sqlbuild.compiler.compile._helpers.render.context_templates import (
    apply_environment_database_schema_overrides,
    build_model_context_values,
    resolve_chained_model_context_templates,
    resolve_early_model_templates,
    resolve_target_context_templates,
)
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
    contains_template_data,
    expand_effective_vars,
    expand_template_data,
)
from sqlbuild.compiler.compile.constants import (
    MACRO_CALL_PATTERN,
    MODEL_FULL_REFRESH_CONFIG_KEY,
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
    DeclarationScopeResolver,
    HookExpansionResult,
    LoadedMacro,
    MacroContext,
    MacroExpansionResult,
    ModelConfigBuildRequest,
    ModelConfigScanCache,
    ModelHeaderColumnCache,
    ModelInputBuildContext,
)
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
from sqlbuild.compiler.planner.types import MaterializationType
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
    ScopeKind,
    UsageKind,
    VisibilityReason,
)
from sqlbuild.spec.contracts.models import (
    DefaultsConfig,
    LocalConfig,
    MaterializationDefaultsConfig,
    ProjectConfig,
    SchemaColumn,
    SchemaModelEntry,
    SchemaSeedEntry,
    SettingsConfig,
    TargetConfig,
)

_HOOK_TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{[^}]+\}")
_LEGACY_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hook", "post_hook"})
_MODEL_HOOK_KEYS: frozenset[str] = frozenset({"pre_hooks", "post_hooks"})
_REUSABLE_MODEL_HEADER_KEYS: frozenset[str] = frozenset({"columns"})
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
    macros: dict[str, LoadedMacro]
    macro_records: dict[str, DeclarationRecord]
    inaccessible_macros: dict[str, DeclarationRecord]


@dataclass
class _VisibleModelDeclarationCache:
    context: ModelInputBuildContext
    reusable_by_parent: bool
    by_parent: dict[Path, _VisibleModelDeclarations] = field(default_factory=dict)

    @classmethod
    def build(cls, context: ModelInputBuildContext) -> _VisibleModelDeclarationCache:
        resolver: DeclarationScopeResolver | None = context.declaration_resolver
        return cls(
            context=context,
            reusable_by_parent=(
                resolver is not None
                and not any(
                    declaration.scope is ScopeKind.PRIVATE
                    for declaration in resolver.lookup.index.declarations
                )
                and not any(
                    resource.kind is ResourceKind.MODEL
                    for resource in resolver.lookup.grants_by_resource
                )
            ),
        )

    def for_model(
        self, *, model_file: DiscoveredSqlModelFile, consumer: ResourceIdentity
    ) -> _VisibleModelDeclarations:
        parent: Path = model_file.file_path.parent
        cached: _VisibleModelDeclarations | None = self.by_parent.get(parent)
        if self.reusable_by_parent and cached is not None:
            return _rebind_visible_declarations(declarations=cached, consumer=consumer)
        resolved: _VisibleModelDeclarations = _build_visible_declaration_indexes(
            model_file=model_file,
            context=self.context,
        )
        if self.reusable_by_parent:
            self.by_parent[parent] = resolved
        return resolved


@dataclass(frozen=True)
class _ModelValidationContext:
    effective_settings: SettingsConfig
    no_sql_validation: bool
    defer_model_sql_validation: bool
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None
    extract_references: Callable[[str], tuple[CompileSqlReference, ...]]
    known_model_names: set[str]
    known_seed_names: set[str]
    known_source_names: set[str]
    known_function_names: set[str]
    known_table_function_names: set[str]
    custom_materialization_names: frozenset[str]


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


@dataclass
class _ReusableModelConfigCache:
    defaults: DefaultsConfig
    path_defaults: dict[str, dict[str, object]]
    target_config: TargetConfig | None
    reusable_by_path_default: dict[str | None, bool] = field(default_factory=dict)
    reusable_metadata_by_identity: dict[int, tuple[object, bool]] = field(default_factory=dict)
    configs: dict[str | None, CompileModelConfig] = field(default_factory=dict)

    def get(
        self,
        *,
        matched_path_default: str | None,
        model_header_values: dict[str, object],
    ) -> CompileModelConfig | None:
        reusable_metadata: dict[str, object] | None = self._reusable_metadata(model_header_values)
        if reusable_metadata is None or not self._is_reusable(matched_path_default):
            return None
        cached: CompileModelConfig | None = self.configs.get(matched_path_default)
        if cached is None:
            return None
        values: dict[str, object] = dict(cached.values)
        values.update(reusable_metadata)
        return replace(cached, values=values)

    def remember(
        self,
        *,
        matched_path_default: str | None,
        model_header_values: dict[str, object],
        config: CompileModelConfig,
    ) -> None:
        reusable_metadata: dict[str, object] | None = self._reusable_metadata(model_header_values)
        if reusable_metadata is None or not self._is_reusable(matched_path_default):
            return
        reusable_values: dict[str, object] = {
            key: value for key, value in config.values.items() if key not in reusable_metadata
        }
        self.configs[matched_path_default] = replace(config, values=reusable_values)

    def _reusable_metadata(
        self,
        model_header_values: dict[str, object],
    ) -> dict[str, object] | None:
        if not model_header_values:
            return {}
        if model_header_values.keys() != _REUSABLE_MODEL_HEADER_KEYS:
            return None
        metadata: object = model_header_values["columns"]
        cached: tuple[object, bool] | None = self.reusable_metadata_by_identity.get(id(metadata))
        if cached is not None and cached[0] is metadata:
            return model_header_values if cached[1] else None
        reusable: bool = not _contains_dynamic_or_unsupported_reusable_metadata(metadata)
        self.reusable_metadata_by_identity[id(metadata)] = (metadata, reusable)
        if not reusable:
            return None
        return model_header_values

    def _is_reusable(self, matched_path_default: str | None) -> bool:
        cached: bool | None = self.reusable_by_path_default.get(matched_path_default)
        if cached is not None:
            return cached
        layered_values: dict[str, object] = build_layered_model_values(
            defaults=self.defaults,
            path_defaults=self.path_defaults,
            matched_path_default=matched_path_default,
            model_header_values={},
        )
        target_namespace_values: tuple[object, object] = (
            None if self.target_config is None else self.target_config.database,
            None if self.target_config is None else self.target_config.schema,
        )
        reusable: bool = not contains_template_data(
            (layered_values, target_namespace_values)
        ) and not _contains_mutable_nested_config(layered_values)
        self.reusable_by_path_default[matched_path_default] = reusable
        return reusable


def _contains_mutable_nested_config(values: dict[str, object]) -> bool:
    if any(key in values for key in _MODEL_HOOK_KEYS):
        return True

    def is_mutable(value: object) -> bool:
        if isinstance(value, dict | list | set):
            return True
        if isinstance(value, tuple):
            return any(is_mutable(item) for item in value)
        return value is not None and not isinstance(value, str | int | float | bool)

    return any(is_mutable(value) for value in values.values())


def _contains_dynamic_or_unsupported_reusable_metadata(value: object) -> bool:
    if isinstance(value, str):
        return contains_template_data(value) or MACRO_CALL_PATTERN.search(value) is not None
    if isinstance(value, dict):
        return any(
            not isinstance(key, str) or _contains_dynamic_or_unsupported_reusable_metadata(item)
            for key, item in value.items()
        )
    if isinstance(value, list | tuple):
        return any(_contains_dynamic_or_unsupported_reusable_metadata(item) for item in value)
    return value is not None and not isinstance(value, int | float | bool)


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

    legacy_schema_files: tuple[DiscoveredSchemaFile, ...] = tuple(
        schema_file for schema_file in discovered_inputs.schema_files if schema_file.model_entries
    )
    with cached_sql_reference_extractor(root=reference_cache_dir) as extract_references:
        return _build_model_inputs(
            discovered_inputs=discovered_inputs,
            context=context,
            no_sql_validation=no_sql_validation,
            defer_model_sql_validation=defer_model_sql_validation,
            external_sql_reference_resolver=external_sql_reference_resolver,
            extract_references=extract_references,
            legacy_schema_files=legacy_schema_files,
        )


def _build_model_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool,
    defer_model_sql_validation: bool,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
    extract_references: Callable[[str], tuple[CompileSqlReference, ...]],
    legacy_schema_files: tuple[DiscoveredSchemaFile, ...],
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
    validation_context: _ModelValidationContext = _ModelValidationContext(
        effective_settings=effective_settings,
        no_sql_validation=no_sql_validation,
        defer_model_sql_validation=defer_model_sql_validation,
        external_sql_reference_resolver=external_sql_reference_resolver,
        extract_references=extract_references,
        known_model_names=known_model_names,
        known_seed_names=known_seed_names,
        known_source_names=known_source_names,
        known_function_names=known_function_names,
        known_table_function_names=known_table_function_names,
        custom_materialization_names=custom_materialization_names,
    )
    sql_hook_definitions: dict[str, DiscoveredSqlHookFile] = _index_sql_hook_definitions(
        discovered_inputs.sql_hook_files
    )
    model_inputs: list[CompileModelInput] = []
    model_header_column_cache: ModelHeaderColumnCache = ModelHeaderColumnCache()
    config_scan_cache: ModelConfigScanCache = ModelConfigScanCache()
    reusable_config_cache: _ReusableModelConfigCache = _ReusableModelConfigCache(
        defaults=discovered_inputs.project_config.defaults,
        path_defaults=discovered_inputs.project_config.path_defaults,
        target_config=target_config,
    )
    declaration_cache: _VisibleModelDeclarationCache = _VisibleModelDeclarationCache.build(context)
    model_file: DiscoveredSqlModelFile
    for model_file in discovered_inputs.model_files:
        model_identity: ResourceIdentity = ResourceIdentity(
            ResourceKind.MODEL, model_file.file_path.stem
        )
        declarations: _VisibleModelDeclarations = declaration_cache.for_model(
            model_file=model_file, consumer=model_identity
        )
        matched_path_default: str | None = find_matching_path_default(
            model_file=model_file,
            path_defaults=discovered_inputs.project_config.path_defaults,
        )
        effective_config: CompileModelConfig | None = reusable_config_cache.get(
            matched_path_default=matched_path_default,
            model_header_values=model_file.header_values,
        )
        if effective_config is None:
            effective_config = build_model_config(
                request=ModelConfigBuildRequest(
                    defaults=discovered_inputs.project_config.defaults,
                    path_defaults=discovered_inputs.project_config.path_defaults,
                    matched_path_default=matched_path_default,
                    model_header_values=model_file.header_values,
                    effective_vars=effective_vars,
                    target_config=target_config,
                    model_name=model_file.file_path.stem,
                    effective_target_name=effective_target_name,
                    run_id=run_id,
                    materialization_defaults=(
                        discovered_inputs.project_config.materialization_defaults
                    ),
                    scan_cache=config_scan_cache,
                )
            )
            reusable_config_cache.remember(
                matched_path_default=matched_path_default,
                model_header_values=model_file.header_values,
                config=effective_config,
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
        declaration_context: DeclarationResolutionContext = DeclarationResolutionContext(
            enums=declarations.enums,
            constants=declarations.constants,
            inaccessible_enums=declarations.inaccessible_enums,
            inaccessible_constants=declarations.inaccessible_constants,
            enum_visibility=declarations.enum_visibility,
            constant_visibility=declarations.constant_visibility,
            macros=declarations.macros,
            macro_records=declarations.macro_records,
            inaccessible_macros=declarations.inaccessible_macros,
            consumer=model_identity,
        )
        declaration_expansion: DeclarationExpansionResult = expand_declaration_references_result(
            sql=var_substituted_sql,
            file_path=model_file.file_path,
            declarations=declaration_context,
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
            declarations=(
                declaration_context if context.declaration_resolver is not None else None
            ),
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
        sql_validation_enabled, references = _validate_model_input(
            context=validation_context,
            model_file=model_file,
            config=effective_config,
            expanded_query_sql=expanded_query_sql,
            sql_validation_placeholders=sql_validation_placeholders,
            model_schema_columns=model_schema_columns,
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
            time_travel_retention=effective_config.time_travel_retention,
            table_type=effective_config.table_type,
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
            audit_factories=discovered_inputs.audit_factories,
            column_cache=model_header_column_cache,
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
        _reject_legacy_schema_match(model_file=model_file, schema_files=legacy_schema_files)
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


def _validate_model_input(
    *,
    context: _ModelValidationContext,
    model_file: DiscoveredSqlModelFile,
    config: CompileModelConfig,
    expanded_query_sql: str,
    sql_validation_placeholders: dict[str, str] | None,
    model_schema_columns: tuple[SchemaColumn, ...] | None,
) -> tuple[bool, tuple[CompileSqlReference, ...]]:
    model_name: str = model_file.file_path.stem
    sql_validation_enabled: bool = _model_sql_validation_gate(
        effective_settings=context.effective_settings,
        no_sql_validation=context.no_sql_validation,
        model_config=config,
    )
    if sql_validation_enabled and not context.defer_model_sql_validation:
        validate_sql_syntax(
            query_sql=cursor_intrinsics_analysis_sql(
                sql=expanded_query_sql,
                cursor_type=config.values.get("cursor_type"),
            ),
            model_name=model_name,
            file_path=model_file.file_path,
            placeholders=sql_validation_placeholders,
        )
    references: tuple[CompileSqlReference, ...] = context.extract_references(expanded_query_sql)
    validate_model_references(
        references=references,
        model_file=model_file,
        known_model_names=context.known_model_names,
        known_seed_names=context.known_seed_names,
        known_source_names=context.known_source_names,
        known_function_names=context.known_function_names,
        known_table_function_names=context.known_table_function_names,
        external_sql_reference_resolver=context.external_sql_reference_resolver,
    )
    validate_incremental_config(
        config=config,
        model_name=model_name,
        ref_count=len(references),
        known_input_names=frozenset(reference.ref_name for reference in references),
        declared_columns=model_schema_columns,
    )
    validate_microbatch_project_capability(
        config=config,
        settings=context.effective_settings,
        model_name=model_name,
    )
    validate_contract_config(config=config, model_name=model_name)
    validate_non_incremental_config(config=config, model_name=model_name)
    validate_snapshot_config(
        config=config,
        model_name=model_name,
        declared_columns=model_schema_columns,
    )
    validate_custom_materialization_config(
        config=config,
        model_name=model_name,
        custom_materialization_names=context.custom_materialization_names,
    )
    validate_storage_policies(config=config, model_name=model_name)
    validate_placeholder_config(
        config=config,
        model_name=model_name,
        query_sql=expanded_query_sql,
        custom_materialization_names=context.custom_materialization_names,
    )
    return sql_validation_enabled, references


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
        macros=visible.macros,
        macro_records=visible.macro_records,
        inaccessible_macros=visible.inaccessible_macros,
    )


def _rebind_visible_declarations(
    *, declarations: _VisibleModelDeclarations, consumer: ResourceIdentity
) -> _VisibleModelDeclarations:
    if not declarations.enum_visibility and not declarations.constant_visibility:
        return declarations
    return replace(
        declarations,
        enum_visibility=_rebind_visibility(
            visibility=declarations.enum_visibility, consumer=consumer
        ),
        constant_visibility=_rebind_visibility(
            visibility=declarations.constant_visibility, consumer=consumer
        ),
    )


def _rebind_visibility(
    *,
    visibility: dict[str, tuple[VisibilityRecord, ...]],
    consumer: ResourceIdentity,
) -> dict[str, tuple[VisibilityRecord, ...]]:
    rebound: dict[str, tuple[VisibilityRecord, ...]] = {}
    for name, records in visibility.items():
        rebound[name] = tuple(replace(record, resource=consumer) for record in records)
    return rebound


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
        connection_name: str | None = target_config.connection_name
        if connection_name is not None:
            if (
                connection_name not in project_config.connections
                and connection_name not in local_config.connections
            ):
                raise CompileInputError(
                    f"Unknown connection '{connection_name}' selected by target. Define "
                    f"[connections.{connection_name}] in sqlbuild_project.toml or "
                    "sqlbuild_local.toml."
                )
            connection.update(project_config.connections.get(connection_name, {}))
            connection.update(local_config.connections.get(connection_name, {}))
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


def build_model_config(*, request: ModelConfigBuildRequest) -> CompileModelConfig:
    """Build the pre-semantic effective model config layers."""

    defaults: DefaultsConfig = request.defaults
    path_defaults: dict[str, dict[str, object]] = request.path_defaults
    matched_path_default: str | None = request.matched_path_default
    model_header_values: dict[str, object] = request.model_header_values
    effective_vars: dict[str, object] = request.effective_vars
    target_config: TargetConfig | None = request.target_config
    model_name: str = request.model_name
    effective_target_name: str | None = request.effective_target_name
    run_id: str = request.run_id
    materialization_defaults: MaterializationDefaultsConfig | None = (
        request.materialization_defaults
    )
    scan_cache: ModelConfigScanCache | None = request.scan_cache

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
    has_authored_templates: bool = _contains_template_data_cached(
        value=layered_values,
        cache=scan_cache.template_presence if scan_cache is not None else None,
    )
    if has_authored_templates:
        early_resolved_values: dict[str, object] = resolve_early_model_templates(
            values=layered_values,
            effective_vars=effective_vars,
            effective_target_name=effective_target_name,
            run_id=run_id,
        )
        model_resolved_values: dict[str, object] = resolve_chained_model_context_templates(
            values=early_resolved_values,
            model_name=model_name,
            effective_target_name=effective_target_name,
            run_id=run_id,
        )
    else:
        model_resolved_values = layered_values
    raw_logical_schema: object | None = model_resolved_values.get("schema")
    raw_logical_database: object | None = model_resolved_values.get("database")
    logical_schema: str | None = raw_logical_schema if isinstance(raw_logical_schema, str) else None
    logical_database: str | None = (
        raw_logical_database if isinstance(raw_logical_database, str) else None
    )
    validate_preserved_logical_namespace(
        resource_label=f"Model '{model_name}'",
        logical_database=logical_database,
        logical_schema=logical_schema,
        target_config=target_config,
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
    target_resolved_values: dict[str, object] = (
        resolve_target_context_templates(
            values=model_resolved_values,
            model_name=model_name,
            effective_target_name=effective_target_name,
            run_id=run_id,
        )
        if has_authored_templates
        or contains_template_data(model_resolved_values.get("database"))
        or contains_template_data(model_resolved_values.get("schema"))
        else model_resolved_values
    )
    target_resolved_values.update(raw_hook_values)
    target_resolved_values, retention, table_type = resolve_storage_policies(
        resolved_values=target_resolved_values,
        model_header_values=model_header_values,
        materialization_defaults=materialization_defaults,
        target_config=target_config,
        model_name=model_name,
    )
    if (
        MODEL_FULL_REFRESH_CONFIG_KEY not in model_header_values
        and target_resolved_values.get("materialized") != MaterializationType.INCREMENTAL
    ):
        target_resolved_values.pop(MODEL_FULL_REFRESH_CONFIG_KEY, None)
    if _contains_model_config_macro_cached(
        values=target_resolved_values,
        cache=scan_cache.macro_presence if scan_cache is not None else None,
    ):
        validate_model_config_has_no_macros(values=target_resolved_values)
    return CompileModelConfig(
        values=target_resolved_values,
        matched_path_default=matched_path_default,
        logical_schema=logical_schema,
        logical_database=logical_database,
        time_travel_retention=retention,
        table_type=table_type,
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
