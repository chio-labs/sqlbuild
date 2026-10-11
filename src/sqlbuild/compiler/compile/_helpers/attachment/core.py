"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass, field, fields, replace
from functools import partial
from inspect import Parameter, Signature
from pathlib import Path
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.attachments.main._pair_native_seed_files import pair_native_seed_files
from sqlbuild.compiler.compile._helpers.analysis.validation import validate_sql_syntax
from sqlbuild.compiler.compile._helpers.attachment.model_config import (
    _model_sql_validation_gate,
    _resolve_model_schema,
    build_model_header_schema_entry,
    find_schema_model_match,
    legacy_schema_rows,
    native_model_config_session,
    strip_model_header_metadata_from_config,
    validate_declared_schema_models_are_attached,
    validate_model_config,
    validate_model_references,
)
from sqlbuild.compiler.compile._helpers.attachment.references import (
    build_known_function_names,
    build_known_ref_names,
    build_known_seed_names,
    build_known_source_names,
    build_known_table_function_names,
)
from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile._helpers.diagnostics.sql_analysis_opt_outs import (
    rejected_sql_analysis_opt_out,
)
from sqlbuild.compiler.compile._helpers.explicit_references.macro_arguments import (
    merge_call_site_references,
    resource_references,
)
from sqlbuild.compiler.compile._helpers.named_declarations.core import (
    named_declaration_usages,
)
from sqlbuild.compiler.compile._helpers.named_declarations.model_schemas import (
    model_schema_enum_declarations,
)
from sqlbuild.compiler.compile._helpers.refs.references import (
    extract_sql_references,
    report_invalid_reference_calls,
    scan_sql_reference_calls,
)
from sqlbuild.compiler.compile._helpers.render.arguments import render_parameterized_sql
from sqlbuild.compiler.compile._helpers.render.context_templates import (
    build_model_context_values,
)
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsic_semantics,
    cursor_intrinsics_analysis_sql,
    get_validated_model_cursor_intrinsics,
    reject_cursor_intrinsics,
)
from sqlbuild.compiler.compile._helpers.render.declarations import (
    expand_scanned_declaration_references,
    render_constant_declaration,
    resolve_declaration_context,
    resolve_enum_contract_columns,
)
from sqlbuild.compiler.compile._helpers.render.macros import (
    expand_sql_macros_result,
)
from sqlbuild.compiler.compile._helpers.render.spans import map_through_passes
from sqlbuild.compiler.compile._helpers.render.sql_vars import (
    applied_interpolation,
    expand_authored_sql_result,
    interpolate_sql_batch,
)
from sqlbuild.compiler.compile._helpers.render.templating import (
    expand_effective_vars,
    expand_template_data,
    record_template_reads,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError, MacroArgumentError
from sqlbuild.compiler.compile.models import (
    AuthoredSqlExpansionResult,
    CompiledSqlExpansion,
    CompileModelConfig,
    CompileModelInput,
    CompileSeedInput,
    CompileSqlReference,
    DeclarationExpansionContext,
    DeclarationExpansionResult,
    DeclarationResolutionContext,
    DeclarationScopeResolver,
    ExpansionSpan,
    HookExpansionResult,
    LoadedMacro,
    MacroContext,
    MacroExpansionResult,
    MappedOffset,
    ModelInputBuildContext,
    ModelResourceNames,
    ModelValidationRequest,
    ModelValidatorContext,
    NativeModelConfigInputs,
    SqlAnalysisOptOutRequest,
    SqlInterpolation,
    SqlReferenceOrigin,
    SqlReferenceScan,
    SqlReferenceSourceMap,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.compiled_project.main._model_input_row import model_input_row
from sqlbuild.compiler.compiled_project.main._model_loop_classes import model_loop_classes
from sqlbuild.compiler.compiled_project.main._plain_model_input import plain_model_input
from sqlbuild.compiler.compiled_project.models import PlainModelFacts
from sqlbuild.compiler.compiled_project.types import PlainSchemaRow, ReferenceRow, SpanRow
from sqlbuild.compiler.discovery.constants import PROJECT_CONFIG_FILENAME
from sqlbuild.compiler.discovery.main._model_query_start import get_model_query_start
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
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.model_config.main._native_contract_classes import native_contract_classes
from sqlbuild.compiler.model_loop.main._scan_native_declaration_references import (
    scan_native_declaration_references,
)
from sqlbuild.compiler.model_loop.types import NativeDeclarationScan
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
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.spec.contracts.models import (
    LocalConfig,
    ProjectConfig,
    SchemaColumn,
    SchemaModelEntry,
    SchemaSeedEntry,
    SettingsConfig,
    SourceLocation,
    TargetConfig,
)

_HOOK_TEMPLATE_PATTERN: re.Pattern[str] = re.compile(r"\$\{[^}]+\}")
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
    macros: dict[str, LoadedMacro]
    macro_records: dict[str, DeclarationRecord]
    inaccessible_macros: dict[str, DeclarationRecord]


@dataclass(frozen=True)
class _ModelValidationContext:
    effective_settings: SettingsConfig
    no_sql_validation: bool
    project_config_path: Path
    defer_model_sql_validation: bool
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None
    sql_lexical_syntax: SqlLexicalSyntax
    known_model_names: set[str]
    known_seed_names: set[str]
    known_source_names: set[str]
    known_function_names: set[str]
    known_table_function_names: set[str]
    custom_materialization_names: frozenset[str]
    validators: ModelValidatorContext


@dataclass(frozen=True)
class _ModelInputLoop:
    discovered_inputs: DiscoveredProjectInputs
    context: ModelInputBuildContext
    validation_context: _ModelValidationContext
    sql_hook_definitions: dict[str, DiscoveredSqlHookFile]
    legacy_schema_files: tuple[DiscoveredSchemaFile, ...]
    native_declaration_references: dict[Path, NativeDeclarationScan]


@dataclass(frozen=True)
class _HookExpansionContext:
    file_path: Path
    effective_vars: dict[str, object]
    context_values: dict[str, str | None]
    loaded_macros: dict[str, LoadedMacro]
    macro_context: MacroContext
    declaration_expansion: DeclarationExpansionContext
    sql_hook_definitions: dict[str, DiscoveredSqlHookFile]
    consumer: ResourceIdentity | DeclarationIdentity
    facts: _HookExpansionFacts
    sql_lexical_syntax: SqlLexicalSyntax
    reference_origin: SqlReferenceOrigin | None = None


@dataclass
class _HookExpansionFacts:
    usages: list[UsageRecord]
    references: list[CompileSqlReference] = field(default_factory=list)

    def add(self, usages: tuple[UsageRecord, ...]) -> None:
        self.usages.extend(usages)

    def add_references(self, references: tuple[CompileSqlReference, ...]) -> None:
        self.references.extend(references)

    def reads_since(self, start: int) -> tuple[SqlResourceRef, ...]:
        return resource_references(tuple(self.references[start:]))


@dataclass
class _ModelLoopHost:
    """The attachment steps the native model loop calls back into, one model index at a time."""

    loop: _ModelInputLoop
    interpolations: dict[Path, SqlInterpolation]
    macros: dict[int, MacroExpansionResult] = field(default_factory=dict)
    python_hooks: dict[int, tuple[UsageRecord, ...]] = field(default_factory=dict)
    hooks: dict[int, HookExpansionResult] = field(default_factory=dict)

    def constant_text(self, *, declaration: ConstantDeclaration, file_path: Path) -> str:
        return render_constant_declaration(
            declaration=declaration,
            value_renderer=self.loop.context.value_renderer,
            collection_rendering=self.loop.context.collection_rendering,
            file_path=file_path,
        )

    def fallback(
        self, *, index: int, config: CompileModelConfig, visible: _VisibleModelDeclarations
    ) -> CompileModelInput:
        model_file: DiscoveredSqlModelFile = self.loop.discovered_inputs.model_files[index]
        return _build_model_input(
            loop=self.loop,
            model_file=model_file,
            interpolation=self.interpolations[model_file.file_path],
            declarations=visible,
            effective_config=config,
            expanded_macros=self.macros.pop(index, None),
            checked_hooks=self.python_hooks.pop(index, None),
            expanded_hooks=self.hooks.pop(index, None),
        )

    def check_hooks(self, *, index: int, config: CompileModelConfig) -> None:
        model_file: DiscoveredSqlModelFile = self.loop.discovered_inputs.model_files[index]
        self.python_hooks[index] = _checked_python_hooks(
            loop=self.loop, model_file=model_file, values=config.values
        )

    def expand_hooks(
        self, *, index: int, config: CompileModelConfig, visible: _VisibleModelDeclarations
    ) -> tuple[dict[str, object], list[ReferenceRow]]:
        expansion: HookExpansionResult = _model_hook_expansion(
            loop=self.loop,
            model_file=self.loop.discovered_inputs.model_files[index],
            declarations=visible,
            config=config,
        )
        self.hooks[index] = expansion
        return expansion.values, [
            (str(item.ref_kind), item.ref_name, item.ref_package, item.call_argument_count)
            for item in expansion.references
        ]

    def expand_macros(
        self, *, index: int, visible: _VisibleModelDeclarations, sql: str, spans: list[SpanRow]
    ) -> tuple[str, list[ReferenceRow], list[SpanRow]]:
        model_file: DiscoveredSqlModelFile = self.loop.discovered_inputs.model_files[index]
        expansion: MacroExpansionResult = _macro_expansion(
            loop=self.loop,
            model_file=model_file,
            declarations=_declaration_context(
                declarations=visible,
                consumer=ResourceIdentity(ResourceKind.MODEL, model_file.file_path.stem),
            ),
            declaration_expansion=DeclarationExpansionResult(
                sql=sql, spans=_expansion_spans(spans), usages=()
            ),
            interpolated_sql=applied_interpolation(self.interpolations[model_file.file_path]),
        )
        self.macros[index] = expansion
        return (
            expansion.sql,
            [
                (str(item.ref_kind), item.ref_name, item.ref_package, item.call_argument_count)
                for item in expansion.argument_references
            ],
            [
                (span.source_start, span.source_end, span.output_start, span.output_end)
                for span in expansion.spans
            ],
        )

    def plain_input(
        self,
        *,
        index: int,
        config: CompileModelConfig,
        visible: _VisibleModelDeclarations,
        values: dict[str, object],
        references: list[ReferenceRow],
        query_sql: str,
        header: tuple[str | None, PlainSchemaRow | None, dict[str, EnumDeclaration]],
        analysis: tuple[bool, SourceLocation | None],
        hook_statements: int,
        declarations: tuple[str, list[SpanRow], list[UsageRecord], list[UsageRecord]],
    ) -> tuple[CompileModelInput, tuple[list[tuple[object, ...]], list[tuple[object, ...]]]]:
        model_file: DiscoveredSqlModelFile = self.loop.discovered_inputs.model_files[index]
        report_native_answer(
            stage=NativeStage.ATTACHMENTS, kind="cursor_intrinsic_rejections", units=hook_statements
        )
        return plain_model_input(
            model_file=model_file,
            interpolation=self.interpolations[model_file.file_path],
            facts=PlainModelFacts(
                config=config,
                values=values,
                references=references,
                query_sql=query_sql,
                description=header[0],
                schema=header[1],
                enum_columns=header[2],
                sql_validation_enabled=analysis[0],
                rejected_sql_analysis_opt_out=analysis[1],
                declaration_sql=declarations[0],
                declaration_spans=_expansion_spans(declarations[1]),
                macro_expansion=self.macros.pop(index, None),
                declaration_usages=tuple(
                    dict.fromkeys(
                        (
                            *dict.fromkeys(declarations[2]),
                            *self._hook_usages(index=index, schema_usages=declarations[3]),
                        )
                    )
                ),
            ),
            declarations=(visible.local_enums, visible.local_constants),
        )

    def _hook_usages(
        self, *, index: int, schema_usages: list[UsageRecord]
    ) -> tuple[UsageRecord, ...]:
        expansion: HookExpansionResult | None = self.hooks.pop(index, None)
        return (
            *(() if expansion is None else expansion.usages),
            *schema_usages,
            *self.python_hooks.pop(index, ()),
        )

    def model_row(self, *, model_input: CompileModelInput) -> tuple[object, ...]:
        return model_input_row(model_input)


def build_model_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool = False,
    defer_model_sql_validation: bool = False,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    native_project: _native.NativeCompiledProject,
) -> tuple[CompileModelInput, ...]:
    """Attach schema metadata to discovered model files."""

    legacy_schema_files: tuple[DiscoveredSchemaFile, ...] = tuple(
        schema_file for schema_file in discovered_inputs.schema_files if schema_file.model_entries
    )
    return _build_model_inputs(
        discovered_inputs=discovered_inputs,
        context=context,
        no_sql_validation=no_sql_validation,
        defer_model_sql_validation=defer_model_sql_validation,
        external_sql_reference_resolver=external_sql_reference_resolver,
        legacy_schema_files=legacy_schema_files,
        native_project=native_project,
    )


def _build_model_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool,
    defer_model_sql_validation: bool,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
    legacy_schema_files: tuple[DiscoveredSchemaFile, ...],
    native_project: _native.NativeCompiledProject,
) -> tuple[CompileModelInput, ...]:
    effective_vars: dict[str, object] = context.effective_vars
    effective_settings: SettingsConfig = context.effective_settings
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
    names: ModelResourceNames = ModelResourceNames(
        models=known_model_names,
        seeds=known_seed_names,
        sources=known_source_names,
        functions=known_function_names,
        table_functions=known_table_function_names,
        custom_materializations=custom_materialization_names,
    )
    validation_context: _ModelValidationContext = _ModelValidationContext(
        effective_settings=effective_settings,
        no_sql_validation=no_sql_validation,
        project_config_path=(discovered_inputs.project_dir or Path()) / PROJECT_CONFIG_FILENAME,
        defer_model_sql_validation=defer_model_sql_validation,
        external_sql_reference_resolver=external_sql_reference_resolver,
        sql_lexical_syntax=context.sql_lexical_syntax,
        known_model_names=known_model_names,
        known_seed_names=known_seed_names,
        known_source_names=known_source_names,
        known_function_names=known_function_names,
        known_table_function_names=known_table_function_names,
        custom_materialization_names=custom_materialization_names,
        validators=ModelValidatorContext(
            names=names,
            settings=effective_settings,
            external_sql_reference_resolver=external_sql_reference_resolver,
            native_config=native_model_config_session(
                inputs=NativeModelConfigInputs(
                    project_config=discovered_inputs.project_config,
                    target_config=context.target_config,
                    effective_vars=effective_vars,
                    effective_target_name=context.effective_target_name,
                    run_id=context.run_id,
                    microbatch_concurrency=effective_settings.microbatch_concurrency,
                ),
                names=names,
            ),
        ),
    )
    sql_hook_definitions: dict[str, DiscoveredSqlHookFile] = _index_sql_hook_definitions(
        discovered_inputs.sql_hook_files
    )
    render_files: tuple[DiscoveredSqlModelFile, ...] = discovered_inputs.model_files
    interpolations: dict[Path, SqlInterpolation] = dict(
        zip(
            (model_file.file_path for model_file in render_files),
            interpolate_sql_batch(
                sqls=tuple(
                    (model_file.query_sql, model_file.file_path) for model_file in render_files
                ),
                effective_vars=effective_vars,
            ),
            strict=True,
        )
    )
    prepared_files: tuple[DiscoveredSqlModelFile, ...] = tuple(
        model_file
        for model_file in render_files
        if interpolations[model_file.file_path].error is None
    )
    report_native_answer(
        stage=NativeStage.MODEL_LOOP, kind="variable_substitutions", units=len(prepared_files)
    )
    loop: _ModelInputLoop = _ModelInputLoop(
        discovered_inputs=discovered_inputs,
        context=context,
        validation_context=validation_context,
        sql_hook_definitions=sql_hook_definitions,
        legacy_schema_files=legacy_schema_files,
        native_declaration_references=dict(
            zip(
                (model_file.file_path for model_file in prepared_files),
                scan_native_declaration_references(
                    sqls=tuple(
                        interpolations[model_file.file_path].sql for model_file in prepared_files
                    )
                ),
                strict=True,
            )
        ),
    )
    model_inputs: list[CompileModelInput] = _run_native_model_loop(
        loop=loop, interpolations=interpolations, native_project=native_project
    )
    validate_declared_schema_models_are_attached(
        model_inputs=tuple(model_inputs),
        schema_files=discovered_inputs.schema_files,
    )
    return tuple(model_inputs)


def _run_native_model_loop(
    *,
    loop: _ModelInputLoop,
    interpolations: dict[Path, SqlInterpolation],
    native_project: _native.NativeCompiledProject,
) -> list[CompileModelInput]:
    """Run the model loop natively; models it cannot finish yet call back into the attachment."""

    files: tuple[DiscoveredSqlModelFile, ...] = loop.discovered_inputs.model_files
    settings: SettingsConfig = loop.validation_context.effective_settings
    native_loop: _native.NativeModelLoop = _native.NativeModelLoop(
        (
            loop.validation_context.validators.native_config.validator,
            native_contract_classes(),
            model_loop_classes(
                audit_factories=loop.discovered_inputs.audit_factories,
                context=loop.context,
                external_resolver=loop.validation_context.external_sql_reference_resolver,
                host_inputs={
                    "report_diagnostic": report_compile_diagnostic,
                    "record_template_reads": record_template_reads,
                    "visible_declarations": _VisibleModelDeclarations,
                    "config_session": loop.validation_context.validators.native_config,
                },
            ),
        ),
        loop.context.sql_lexical_syntax.native_mapping,
        cursor_intrinsic_semantics(),
        (
            (
                settings.sql_analysis,
                loop.validation_context.no_sql_validation,
                loop.validation_context.defer_model_sql_validation,
                settings.require_sql_analysis,
            ),
            native_stage_enabled(NativeStage.PROJECT_ASSEMBLY),
            (
                str(loop.validation_context.project_config_path),
                legacy_schema_rows(loop.legacy_schema_files),
            ),
        ),
    )
    host: _ModelLoopHost = _ModelLoopHost(loop=loop, interpolations=interpolations)
    inputs, (finished_natively, config_builds, declaration_contexts) = native_loop.run(
        native_project,
        host,
        [
            (
                (
                    model_file.file_path.stem,
                    model_file.relative_path.as_posix(),
                    str(model_file.relative_path),
                    str(model_file.file_path),
                ),
                (
                    model_file.header_column_locations,
                    model_file.header_values,
                    model_file.enum_declarations,
                    model_file.constant_declarations,
                ),
                model_file.query_sql,
                model_file.contents,
                loop.native_declaration_references.get(model_file.file_path),
                _interpolation_row(interpolations[model_file.file_path]),
            )
            for model_file in files
        ],
    )
    report_native_answer(stage=NativeStage.MODEL_CONFIG, kind="config_builds", units=config_builds)
    report_native_answer(
        stage=NativeStage.MODEL_LOOP, kind="declaration_contexts", units=declaration_contexts
    )
    report_native_answer(
        stage=NativeStage.MODEL_LOOP, kind="native_model_inputs", units=finished_natively
    )
    return list(inputs)


def _interpolation_row(
    interpolation: SqlInterpolation,
) -> tuple[str, list[tuple[str, str]], str | None]:
    return interpolation.sql, list(interpolation.reads), interpolation.error


def _expansion_spans(rows: list[SpanRow]) -> tuple[ExpansionSpan, ...]:
    return tuple(
        ExpansionSpan(
            source_start=source_start,
            source_end=source_end,
            output_start=output_start,
            output_end=output_end,
        )
        for source_start, source_end, output_start, output_end in rows
    )


def _checked_python_hooks(
    *, loop: _ModelInputLoop, model_file: DiscoveredSqlModelFile, values: dict[str, object]
) -> tuple[UsageRecord, ...]:
    """Check the model's Python hooks against their functions and return their usages."""

    discovered_inputs: DiscoveredProjectInputs = loop.discovered_inputs
    validate_python_hook_config(
        values=values,
        model_name=model_file.file_path.stem,
        hook_functions=discovered_inputs.hook_functions,
        provider_names=frozenset(provider.name for provider in discovered_inputs.providers),
    )
    return _python_hook_usages(
        values=values,
        resolver=loop.context.declaration_resolver,
        consumer=ResourceIdentity(ResourceKind.MODEL, model_file.file_path.stem),
        consumer_path=model_file.relative_path,
    )


def _model_hook_expansion(
    *,
    loop: _ModelInputLoop,
    model_file: DiscoveredSqlModelFile,
    declarations: _VisibleModelDeclarations,
    config: CompileModelConfig,
) -> HookExpansionResult:
    """Expand the model's hook macros and declarations, as the project's macros render them."""

    context: ModelInputBuildContext = loop.context
    return expand_model_hook_macros_result(
        values=config.values,
        model_file=_model_reference_origin(model_file=model_file),
        effective_vars=context.effective_vars,
        context_values=build_model_context_values(
            values=config.values,
            model_name=model_file.file_path.stem,
            effective_target_name=context.effective_target_name,
            run_id=context.run_id,
            include_target_values=True,
        ),
        loaded_macros=context.loaded_macros,
        macro_context=context.macro_context,
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
        sql_lexical_syntax=context.sql_lexical_syntax,
        sql_hook_definitions=loop.sql_hook_definitions,
        consumer=ResourceIdentity(ResourceKind.MODEL, model_file.file_path.stem),
    )


def _declaration_context(
    *, declarations: _VisibleModelDeclarations, consumer: ResourceIdentity
) -> DeclarationResolutionContext:
    return DeclarationResolutionContext(
        enums=declarations.enums,
        constants=declarations.constants,
        inaccessible_enums=declarations.inaccessible_enums,
        inaccessible_constants=declarations.inaccessible_constants,
        enum_visibility=declarations.enum_visibility,
        constant_visibility=declarations.constant_visibility,
        macros=declarations.macros,
        macro_records=declarations.macro_records,
        inaccessible_macros=declarations.inaccessible_macros,
        consumer=consumer,
    )


def _macro_expansion(
    *,
    loop: _ModelInputLoop,
    model_file: DiscoveredSqlModelFile,
    declarations: DeclarationResolutionContext,
    declaration_expansion: DeclarationExpansionResult,
    interpolated_sql: str,
) -> MacroExpansionResult:
    """Expand the model's macro calls, locating argument errors in the authored query."""

    context: ModelInputBuildContext = loop.context
    try:
        return expand_sql_macros_result(
            sql=declaration_expansion.sql,
            file_path=model_file.file_path,
            loaded_macros=context.loaded_macros,
            macro_context=context.macro_context,
            declaration_resolver=context.declaration_resolver,
            declarations=declarations if context.declaration_resolver is not None else None,
            consumer=declarations.consumer,
        )
    except MacroArgumentError as error:
        location: SourceLocation | None = (
            _authored_model_location(
                model_file=model_file,
                sql=declaration_expansion.sql,
                offset=error.offset,
                passes=(declaration_expansion.spans,),
            )
            if interpolated_sql == model_file.query_sql
            else None
        )
        if location is None:
            raise
        raise error.located(location) from None


def _build_model_input(
    *,
    loop: _ModelInputLoop,
    model_file: DiscoveredSqlModelFile,
    interpolation: SqlInterpolation,
    declarations: _VisibleModelDeclarations,
    effective_config: CompileModelConfig,
    expanded_macros: MacroExpansionResult | None,
    checked_hooks: tuple[UsageRecord, ...] | None,
    expanded_hooks: HookExpansionResult | None,
) -> CompileModelInput:
    discovered_inputs: DiscoveredProjectInputs = loop.discovered_inputs
    context: ModelInputBuildContext = loop.context
    validation_context: _ModelValidationContext = loop.validation_context
    legacy_schema_files: tuple[DiscoveredSchemaFile, ...] = loop.legacy_schema_files
    model_identity: ResourceIdentity = ResourceIdentity(
        ResourceKind.MODEL, model_file.file_path.stem
    )
    model_schema: ModelSchemaDeclaration | None = _resolve_model_schema(
        values=effective_config.values,
        model_name=model_file.file_path.stem,
        public_model_schemas=context.public_model_schemas,
    )
    model_schema_columns: tuple[SchemaColumn, ...] | None = (
        model_schema.columns if model_schema is not None else None
    )
    python_hook_usages: tuple[UsageRecord, ...] = (
        _checked_python_hooks(loop=loop, model_file=model_file, values=effective_config.values)
        if checked_hooks is None
        else checked_hooks
    )
    named_usages: tuple[UsageRecord, ...] = (
        *(
            named_declaration_usages(
                resolver=context.declaration_resolver,
                kind=DeclarationKind.SCHEMA,
                name=model_schema.name,
                consumer=model_identity,
                consumer_path=model_file.relative_path,
            )
            if model_schema is not None
            else ()
        ),
        *python_hook_usages,
    )
    var_substituted_sql: str = applied_interpolation(interpolation)
    declaration_context: DeclarationResolutionContext = _declaration_context(
        declarations=declarations, consumer=model_identity
    )
    declaration_expansion: DeclarationExpansionResult = expand_scanned_declaration_references(
        sql=var_substituted_sql,
        references=loop.native_declaration_references[model_file.file_path],
        file_path=model_file.file_path,
        declarations=declaration_context,
        value_renderer=context.value_renderer,
        collection_rendering=context.collection_rendering,
    )
    report_native_answer(stage=NativeStage.MODEL_LOOP, kind="declaration_expansions")
    declaration_expanded_sql: str = declaration_expansion.sql
    macro_expansion: MacroExpansionResult = (
        _macro_expansion(
            loop=loop,
            model_file=model_file,
            declarations=declaration_context,
            declaration_expansion=declaration_expansion,
            interpolated_sql=var_substituted_sql,
        )
        if expanded_macros is None
        else expanded_macros
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
    sql_validation_enabled, references, rejected_opt_out = _validate_model_input(
        context=validation_context,
        model_file=model_file,
        config=effective_config,
        expanded_query_sql=expanded_query_sql,
        sql_validation_placeholders=sql_validation_placeholders,
        model_schema_columns=model_schema_columns,
        argument_references=macro_expansion.argument_references,
        reference_source_map=(
            SqlReferenceSourceMap(
                body_start=partial(
                    get_model_query_start,
                    contents=model_file.contents,
                    query_sql=model_file.query_sql,
                ),
                passes=(declaration_expansion.spans, macro_expansion.spans),
            )
            if var_substituted_sql == model_file.query_sql
            and expanded_query_sql == macro_expansion.sql
            else None
        ),
    )
    hook_expansion: HookExpansionResult = (
        _model_hook_expansion(
            loop=loop, model_file=model_file, declarations=declarations, config=effective_config
        )
        if expanded_hooks is None
        else expanded_hooks
    )
    expanded_config: CompileModelConfig = _hook_expanded_config(
        config=effective_config,
        hook_expansion=hook_expansion,
        model_file=model_file,
        validation_context=validation_context,
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
    )
    model_config: CompileModelConfig = strip_model_header_metadata_from_config(expanded_config)
    header_schema_entry, enum_columns = resolve_enum_contract_columns(
        schema_entry=header_schema_entry,
        config_values=model_config.values,
        enums=(
            declarations.enums
            if model_schema is None
            else {
                **declarations.enums,
                **model_schema_enum_declarations(
                    schema=model_schema, resolver=context.declaration_resolver
                ),
            }
        ),
    )
    generated_usages: tuple[UsageRecord, ...] = _generated_enum_usages(
        enum_columns=enum_columns,
        declarations=declarations,
        consumer=model_identity,
    )
    model_declaration_usages: tuple[UsageRecord, ...] = tuple(
        dict.fromkeys(
            (
                *declaration_expansion.usages,
                *generated_usages,
                *hook_expansion.usages,
                *named_usages,
            )
        )
    )
    _reject_legacy_schema_match(model_file=model_file, schema_files=legacy_schema_files)
    lint_expansion: CompiledSqlExpansion = CompiledSqlExpansion(
        authored_sql=model_file.query_sql,
        expanded_sql=macro_expansion.sql,
        passes=(interpolation.spans, declaration_expansion.spans, macro_expansion.spans),
    )
    if header_schema_entry is None:
        return CompileModelInput(
            sql_expansion=(
                CompiledSqlExpansion(
                    authored_sql=model_file.query_sql,
                    expanded_sql=macro_expansion.sql,
                    passes=(declaration_expansion.spans, macro_expansion.spans),
                )
                if var_substituted_sql == model_file.query_sql
                else None
            ),
            model_file=model_file,
            config=model_config,
            query_sql=expanded_query_sql,
            macro_source_sql=declaration_expanded_sql,
            references=references,
            sql_validation_enabled=sql_validation_enabled,
            rejected_sql_analysis_opt_out=rejected_opt_out,
            enum_declarations=tuple(declarations.local_enums.values()),
            constant_declarations=tuple(declarations.local_constants.values()),
            enum_columns=enum_columns,
            macro_deps=tuple(item.name for item in macro_expansion.dependencies),
            macro_usages=macro_expansion.usages,
            declaration_usages=model_declaration_usages,
            lint_expansion=lint_expansion,
        )

    return CompileModelInput(
        sql_expansion=(
            CompiledSqlExpansion(
                authored_sql=model_file.query_sql,
                expanded_sql=macro_expansion.sql,
                passes=(declaration_expansion.spans, macro_expansion.spans),
            )
            if var_substituted_sql == model_file.query_sql
            else None
        ),
        model_file=model_file,
        config=model_config,
        query_sql=expanded_query_sql,
        macro_source_sql=declaration_expanded_sql,
        references=references,
        schema_entry=header_schema_entry,
        sql_validation_enabled=sql_validation_enabled,
        rejected_sql_analysis_opt_out=rejected_opt_out,
        enum_declarations=tuple(declarations.local_enums.values()),
        constant_declarations=tuple(declarations.local_constants.values()),
        enum_columns=enum_columns,
        macro_deps=tuple(item.name for item in macro_expansion.dependencies),
        macro_usages=macro_expansion.usages,
        declaration_usages=model_declaration_usages,
        lint_expansion=lint_expansion,
    )


def _hook_expanded_config(
    *,
    config: CompileModelConfig,
    hook_expansion: HookExpansionResult,
    model_file: DiscoveredSqlModelFile,
    validation_context: _ModelValidationContext,
) -> CompileModelConfig:
    validate_model_references(
        context=validation_context.validators,
        model_file=model_file,
        references=hook_expansion.references,
    )
    return CompileModelConfig(
        values=hook_expansion.values,
        model_header_keys=config.model_header_keys,
        matched_path_default=config.matched_path_default,
        logical_schema=config.logical_schema,
        layer_schema=config.layer_schema,
        logical_database=config.logical_database,
        time_travel_retention=config.time_travel_retention,
        table_type=config.table_type,
    )


def _model_reference_origin(
    *, model_file: DiscoveredSqlModelFile, source_map: SqlReferenceSourceMap | None = None
) -> SqlReferenceOrigin:
    return SqlReferenceOrigin(
        file_path=model_file.file_path,
        relative_path=model_file.relative_path,
        contents=model_file.contents,
        resource_type=CompiledResourceType.MODEL,
        resource_name=model_file.file_path.stem,
        source_map=source_map,
    )


def _validate_model_input(
    *,
    context: _ModelValidationContext,
    model_file: DiscoveredSqlModelFile,
    config: CompileModelConfig,
    expanded_query_sql: str,
    sql_validation_placeholders: dict[str, str] | None,
    model_schema_columns: tuple[SchemaColumn, ...] | None,
    argument_references: tuple[CompileSqlReference, ...],
    reference_source_map: SqlReferenceSourceMap | None,
) -> tuple[bool, tuple[CompileSqlReference, ...], SourceLocation | None]:
    model_name: str = model_file.file_path.stem
    sql_validation_enabled: bool = _model_sql_validation_gate(
        effective_settings=context.effective_settings,
        no_sql_validation=context.no_sql_validation,
        model_config=config,
    )
    rejected_opt_out: SourceLocation | None = (
        None
        if sql_validation_enabled
        else rejected_sql_analysis_opt_out(
            SqlAnalysisOptOutRequest(
                model_file=model_file,
                config=config,
                settings=context.effective_settings,
                no_sql_validation=context.no_sql_validation,
                query_sql=cursor_intrinsics_analysis_sql(
                    sql=expanded_query_sql, cursor_type=config.values.get("cursor_type")
                ),
                placeholders=sql_validation_placeholders,
                project_config_path=context.project_config_path,
            )
        )
    )
    sql_validation_enabled = sql_validation_enabled or rejected_opt_out is not None
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
    reference_origin: SqlReferenceOrigin = _model_reference_origin(
        model_file=model_file, source_map=reference_source_map
    )
    reference_scan: SqlReferenceScan = scan_sql_reference_calls(
        sql=expanded_query_sql, syntax=context.sql_lexical_syntax, origin=reference_origin
    )
    report_invalid_reference_calls(
        invalid_calls=reference_scan.invalid_calls,
        origin=reference_origin,
        syntax=context.sql_lexical_syntax,
    )
    references: tuple[CompileSqlReference, ...] = merge_call_site_references(
        references=reference_scan.references,
        argument_references=argument_references,
    )
    validate_model_config(
        context=context.validators,
        request=ModelValidationRequest(
            model_file=model_file,
            config=config,
            references=references,
            declared_columns=model_schema_columns,
            query_sql=expanded_query_sql,
        ),
    )
    return (
        sql_validation_enabled and not reference_scan.invalid_calls,
        references,
        rejected_opt_out,
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

    if native_stage_enabled(NativeStage.ATTACHMENTS):
        return _native_seed_inputs(
            seed_declarations=seed_declarations, seed_files=discovered_inputs.seed_files
        )
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


def _native_seed_inputs(
    *,
    seed_declarations: list[tuple[SchemaSeedEntry, DiscoveredSchemaFile]],
    seed_files: tuple[DiscoveredSeedFile, ...],
) -> tuple[CompileSeedInput, ...]:
    pairs: list[int] | None
    missing: int | None
    pairs, missing = pair_native_seed_files(
        declaration_names=[seed_entry.name for seed_entry, _ in seed_declarations],
        file_stems=[seed_file.file_path.stem for seed_file in seed_files],
    )
    if pairs is None:
        seed_entry, seed_schema_file = seed_declarations[cast(int, missing)]
        raise CompileInputError(
            f"Seed declaration '{seed_entry.name}' in {seed_schema_file.relative_path} "
            "has no matching CSV file under seeds/",
        )
    report_native_answer(stage=NativeStage.ATTACHMENTS, kind="seed_pairs", units=len(pairs))
    return tuple(
        CompileSeedInput(
            seed_file=seed_files[file_index],
            schema_entry=seed_entry,
            schema_file=seed_schema_file,
        )
        for (seed_entry, seed_schema_file), file_index in zip(seed_declarations, pairs, strict=True)
    )


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


def expand_model_hook_macros_result(
    *,
    values: dict[str, object],
    model_file: SqlReferenceOrigin,
    effective_vars: dict[str, object],
    context_values: dict[str, str | None],
    loaded_macros: dict[str, LoadedMacro],
    macro_context: MacroContext,
    declaration_expansion: DeclarationExpansionContext,
    sql_lexical_syntax: SqlLexicalSyntax,
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
                file_path=model_file.file_path,
                effective_vars=effective_vars,
                context_values=context_values,
                loaded_macros=loaded_macros,
                macro_context=macro_context,
                declaration_expansion=declaration_expansion,
                sql_hook_definitions=sql_hook_definitions or {},
                consumer=consumer
                or ResourceIdentity(ResourceKind.MODEL, model_file.file_path.stem),
                facts=facts,
                sql_lexical_syntax=sql_lexical_syntax,
                reference_origin=model_file,
            ),
            hook_key=hook_key,
        )
    return HookExpansionResult(
        values=expanded_values,
        usages=tuple(dict.fromkeys(facts.usages)),
        references=tuple(dict.fromkeys(facts.references)),
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


def _python_hook_usages(
    *,
    values: dict[str, object],
    resolver: DeclarationScopeResolver | None,
    consumer: ResourceIdentity,
    consumer_path: Path,
) -> tuple[UsageRecord, ...]:
    usages: list[UsageRecord] = []
    hook_key: str
    for hook_key in sorted(_MODEL_HOOK_KEYS):
        raw_value: object | None = values.get(hook_key)
        if not isinstance(raw_value, list | tuple):
            continue
        hook_entry: object
        for hook_entry in raw_value:
            if isinstance(hook_entry, PythonHookEntry):
                usages.extend(
                    named_declaration_usages(
                        resolver=resolver,
                        kind=DeclarationKind.PYTHON_HOOK,
                        name=hook_entry.name,
                        consumer=consumer,
                        consumer_path=consumer_path,
                    )
                )
    return tuple(usages)


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
        facts.add_references(
            merge_call_site_references(
                references=extract_sql_references(
                    sql=expansion.sql,
                    syntax=context.sql_lexical_syntax,
                    origin=context.reference_origin,
                ),
                argument_references=expansion.argument_references,
            )
        )
        return expansion.sql
    if isinstance(value, SqlHookEntry):
        inline_start: int = len(context.facts.references)
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
            reads=context.facts.reads_since(inline_start),
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
        hook_facts: _HookExpansionFacts = context.facts
        hook_facts.add(
            named_declaration_usages(
                resolver=context.declaration_expansion.resolver,
                kind=DeclarationKind.SQL_HOOK,
                name=value.name,
                consumer=context.consumer,
                consumer_path=context.file_path,
            )
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
        named_start: int = len(hook_facts.references)
        expanded_statement = expand_sql_macros_in_value(
            value=rendered_statement,
            context=replace(
                context,
                file_path=hook_definition.file_path,
                consumer=DeclarationIdentity(DeclarationKind.SQL_HOOK, value.name),
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
            reads=hook_facts.reads_since(named_start),
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


def _authored_model_location(
    *,
    model_file: DiscoveredSqlModelFile,
    sql: str,
    offset: int,
    passes: tuple[tuple[ExpansionSpan, ...], ...],
) -> SourceLocation | None:
    """Map an offset in expanded model SQL to its authored file location, if it is authored."""

    contents: str = model_file.contents
    body_start: int | None = get_model_query_start(
        contents=contents, query_sql=model_file.query_sql
    )
    if body_start is None and contents.lstrip().startswith(model_file.query_sql):
        body_start = len(contents) - len(contents.lstrip())
    mapped: MappedOffset = map_through_passes(offset=offset, passes=passes)
    authored_offset: int = (body_start or 0) + mapped.offset
    if (
        body_start is None
        or mapped.generated
        or offset >= len(sql)
        or authored_offset >= len(contents)
        or contents[authored_offset] != sql[offset]
    ):
        return None
    return SourceLocation(
        path=model_file.relative_path,
        line=contents.count("\n", 0, authored_offset) + 1,
        column=authored_offset - (contents.rfind("\n", 0, authored_offset) + 1) + 1,
    )
