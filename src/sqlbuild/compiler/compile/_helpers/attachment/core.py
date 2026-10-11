"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.attachments.main._pair_native_seed_files import pair_native_seed_files
from sqlbuild.compiler.authored_values.main._project_var_values import render_project_var_text
from sqlbuild.compiler.compile._helpers.analysis.validation import sql_analysis_opt_out_help
from sqlbuild.compiler.compile._helpers.attachment.model_config import (
    legacy_schema_rows,
    native_model_config_session,
    validate_declared_schema_models_are_attached,
)
from sqlbuild.compiler.compile._helpers.attachment.references import (
    build_known_function_names,
    build_known_ref_names,
    build_known_seed_names,
    build_known_source_names,
    build_known_table_function_names,
)
from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsic_semantics,
)
from sqlbuild.compiler.compile._helpers.render.declarations import (
    render_constant_declaration,
)
from sqlbuild.compiler.compile._helpers.render.macros import (
    macro_expansion_classes,
)
from sqlbuild.compiler.compile._helpers.render.sql_vars import (
    interpolate_sql_batch,
)
from sqlbuild.compiler.compile._helpers.render.templating import (
    expand_effective_vars,
    expand_template_data,
    record_template_reads,
)
from sqlbuild.compiler.compile.classes.unicode_environment import UnicodeEnvironment
from sqlbuild.compiler.compile.constants import EXPLICIT_REFERENCE_KINDS
from sqlbuild.compiler.compile.exceptions import CompileInputError, MacroArgumentError
from sqlbuild.compiler.compile.models import (
    CompileModelConfig,
    CompileModelInput,
    CompileSeedInput,
    DeclarationResolutionContext,
    ExpansionSpan,
    LoadedMacro,
    MacroExpansionResult,
    ModelInputBuildContext,
    ModelResourceNames,
    ModelValidatorContext,
    NativeModelConfigInputs,
    SqlInterpolation,
)
from sqlbuild.compiler.compiled_project.main._model_loop_classes import model_loop_classes
from sqlbuild.compiler.compiled_project.main._plain_model_input import plain_model_input
from sqlbuild.compiler.compiled_project.models import PlainModelFacts
from sqlbuild.compiler.compiled_project.types import PlainSchemaRow, ReferenceRow, SpanRow
from sqlbuild.compiler.discovery.constants import PROJECT_CONFIG_FILENAME
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredProjectInputs,
    DiscoveredSchemaFile,
    DiscoveredSeedFile,
    DiscoveredSqlHookFile,
    DiscoveredSqlModelFile,
    EnumDeclaration,
    NamedSqlHookEntry,
    PythonHookEntry,
)
from sqlbuild.compiler.frontier.main.report_native_answer import report_native_answer
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.macro_bridge.main.active_macro_bridge import active_macro_bridge
from sqlbuild.compiler.model_config.main._native_contract_classes import native_contract_classes
from sqlbuild.compiler.model_loop.main._scan_native_declaration_references import (
    scan_native_declaration_references,
)
from sqlbuild.compiler.model_loop.types import NativeDeclarationScan
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    UsageRecord,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.spec.contracts.models import (
    LocalConfig,
    ProjectConfig,
    SchemaSeedEntry,
    SettingsConfig,
    SourceLocation,
    TargetConfig,
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


@dataclass
class _ModelLoopHost:
    """The attachment steps the native model loop calls back into, one model index at a time."""

    loop: _ModelInputLoop
    interpolations: dict[Path, SqlInterpolation]

    def constant_text(self, *, declaration: ConstantDeclaration, file_path: Path) -> str:
        return render_constant_declaration(
            declaration=declaration,
            value_renderer=self.loop.context.value_renderer,
            collection_rendering=self.loop.context.collection_rendering,
            file_path=file_path,
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
        declarations: tuple[
            str,
            list[SpanRow],
            list[UsageRecord],
            list[UsageRecord],
            tuple[str, list[SpanRow], list[DeclarationIdentity], list[UsageRecord]] | None,
        ],
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
                macro_expansion=_native_macro_expansion(declarations[4]),
                declaration_usages=tuple(
                    dict.fromkeys(
                        (
                            *dict.fromkeys(declarations[2]),
                            *declarations[3],
                        )
                    )
                ),
            ),
            declarations=(visible.local_enums, visible.local_constants),
        )


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
                    "syntax_help": sql_analysis_opt_out_help(model_owned=True),
                    "macros": {
                        "loaded_macros": loop.context.loaded_macros,
                        "macro_context": loop.context.macro_context,
                        "bridge": active_macro_bridge(),
                        "scoped": loop.context.declaration_resolver is not None,
                        "declaration_context": DeclarationResolutionContext,
                        "macro_argument_error": MacroArgumentError,
                        "expansion": macro_expansion_classes(),
                        "generic_syntax": SqlLexicalSyntax().native_mapping,
                    },
                    "sql_hooks": {
                        "named_sql_hook_entry": NamedSqlHookEntry,
                        "python_hook_entry": PythonHookEntry,
                        "definitions": loop.sql_hook_definitions,
                        "effective_vars": loop.context.effective_vars,
                        "environment": UnicodeEnvironment(),
                        "render_project_var": render_project_var_text,
                        "sql_resource_ref": SqlResourceRef,
                        "explicit_kinds": EXPLICIT_REFERENCE_KINDS,
                        "declaration_identity": DeclarationIdentity,
                        "sql_hook_kind": DeclarationKind.SQL_HOOK,
                    },
                    "hook_functions": loop.discovered_inputs.hook_functions,
                    "provider_names": frozenset(
                        provider.name for provider in loop.discovered_inputs.providers
                    ),
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


def _native_macro_expansion(
    row: tuple[str, list[SpanRow], list[DeclarationIdentity], list[UsageRecord]] | None,
) -> MacroExpansionResult | None:
    if row is None:
        return None
    sql, spans, dependencies, usages = row
    return MacroExpansionResult(
        sql=sql,
        spans=_expansion_spans(spans),
        dependencies=tuple(dict.fromkeys(dependencies)),
        usages=tuple(dict.fromkeys(usages)),
    )


def build_seed_inputs(discovered_inputs: DiscoveredProjectInputs) -> tuple[CompileSeedInput, ...]:
    """Attach seed declarations to discovered seed CSV files."""

    seed_declarations: list[tuple[SchemaSeedEntry, DiscoveredSchemaFile]] = []
    schema_file: DiscoveredSchemaFile
    for schema_file in discovered_inputs.schema_files:
        seed_entry: SchemaSeedEntry
        for seed_entry in schema_file.seed_entries:
            seed_declarations.append((seed_entry, schema_file))

    return _native_seed_inputs(
        seed_declarations=seed_declarations, seed_files=discovered_inputs.seed_files
    )


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
