"""Attachment helpers for building pre-semantic compile inputs."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.authored_values.main._project_var_values import render_project_var_text
from sqlbuild.compiler.compile._helpers.analysis.validation import sql_analysis_opt_out_help
from sqlbuild.compiler.compile._helpers.attachment.model_config import (
    native_model_config_session,
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
from sqlbuild.compiler.compile._helpers.render.templating import (
    expand_effective_vars,
    expand_template_data,
    record_template_reads,
)
from sqlbuild.compiler.compile.classes.unicode_environment import UnicodeEnvironment
from sqlbuild.compiler.compile.constants import EXPLICIT_REFERENCE_KINDS
from sqlbuild.compiler.compile.exceptions import CompileInputError, MacroArgumentError
from sqlbuild.compiler.compile.models import (
    DeclarationResolutionContext,
    LoadedMacro,
    ModelInputBuildContext,
    ModelValidatorContext,
    NativeModelConfigInputs,
)
from sqlbuild.compiler.compile.types import ModelInput
from sqlbuild.compiler.compiled_project.main._model_loop_classes import model_loop_classes
from sqlbuild.compiler.discovery.constants import PROJECT_CONFIG_FILENAME
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredProjectInputs,
    DiscoveredSqlModelFile,
    EnumDeclaration,
    NamedSqlHookEntry,
    PythonHookEntry,
)
from sqlbuild.compiler.macro_bridge.main.active_macro_bridge import active_macro_bridge
from sqlbuild.compiler.model_config.main._native_contract_classes import native_contract_classes
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
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
    SettingsConfig,
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
    validators: ModelValidatorContext


@dataclass(frozen=True)
class _ModelInputLoop:
    discovered_inputs: DiscoveredProjectInputs
    context: ModelInputBuildContext
    validation_context: _ModelValidationContext


@dataclass
class _ModelLoopHost:
    """The attachment steps the native model loop calls back into, one model index at a time."""

    loop: _ModelInputLoop

    def constant_text(self, *, declaration: ConstantDeclaration, file_path: Path) -> str:
        return render_constant_declaration(
            declaration=declaration,
            value_renderer=self.loop.context.value_renderer,
            collection_rendering=self.loop.context.collection_rendering,
            file_path=file_path,
        )


def build_model_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool = False,
    defer_model_sql_validation: bool = False,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    native_project: _native.NativeCompiledProject,
) -> tuple[ModelInput, ...]:
    """Attach schema metadata to discovered model files."""

    return _build_model_inputs(
        discovered_inputs=discovered_inputs,
        context=context,
        no_sql_validation=no_sql_validation,
        defer_model_sql_validation=defer_model_sql_validation,
        external_sql_reference_resolver=external_sql_reference_resolver,
        native_project=native_project,
    )


def _build_model_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool,
    defer_model_sql_validation: bool,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
    native_project: _native.NativeCompiledProject,
) -> tuple[ModelInput, ...]:
    effective_vars: dict[str, object] = context.effective_vars
    effective_settings: SettingsConfig = context.effective_settings
    validator: _native.NativeModelValidator = _native.NativeModelValidator.from_inputs(
        discovered_inputs, effective_settings.microbatch_concurrency
    )
    if external_sql_reference_resolver is not None:
        external_sql_reference_resolver.validate_model_names(
            known_model_names=validator.model_names()
        )
    validation_context: _ModelValidationContext = _ModelValidationContext(
        effective_settings=effective_settings,
        no_sql_validation=no_sql_validation,
        project_config_path=(discovered_inputs.project_dir or Path()) / PROJECT_CONFIG_FILENAME,
        defer_model_sql_validation=defer_model_sql_validation,
        external_sql_reference_resolver=external_sql_reference_resolver,
        sql_lexical_syntax=context.sql_lexical_syntax,
        validators=ModelValidatorContext(
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
                validator=validator,
            ),
        ),
    )
    loop: _ModelInputLoop = _ModelInputLoop(
        discovered_inputs=discovered_inputs,
        context=context,
        validation_context=validation_context,
    )
    return tuple(_run_native_model_loop(loop=loop, native_project=native_project))


def _run_native_model_loop(
    *, loop: _ModelInputLoop, native_project: _native.NativeCompiledProject
) -> list[ModelInput]:
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
                    "source_syntax_help": sql_analysis_opt_out_help(model_owned=False),
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
                        "hook_files": loop.discovered_inputs.sql_hook_files,
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
            str(loop.validation_context.project_config_path),
        ),
    )
    inputs: list[_native.NativeModelInput] = native_loop.run(
        native_project, _ModelLoopHost(loop=loop), list(files)
    )
    return list(inputs)


def build_effective_connection(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    target_config: TargetConfig | None,
    effective_vars: dict[str, object],
) -> dict[str, object]:
    """Merge base project connection with the selected environment overrides."""

    connection, error = _native.effective_config_connection(
        project_config, local_config, target_config
    )
    if connection is None:
        raise CompileInputError(error or "")
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

    values: dict[str, object] = _native.effective_config_settings(
        (project_config.settings, local_config.settings),
        local_config.setting_overrides,
        [field.name for field in fields(SettingsConfig)],
    )
    return SettingsConfig(**cast(dict[str, Any], values))


def build_effective_vars(
    *,
    project_config: ProjectConfig,
    local_config: LocalConfig,
    target_config: TargetConfig | None,
    cli_vars: dict[str, object],
) -> dict[str, object]:
    """Merge effective vars using the locked precedence order."""

    return expand_effective_vars(
        _native.effective_config_vars((project_config, local_config), target_config, cli_vars)
    )
