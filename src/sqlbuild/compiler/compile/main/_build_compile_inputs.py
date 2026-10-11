"""Build the first attached compile input snapshot from discovered inputs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.attachment.core import (
    build_effective_connection,
    build_effective_settings,
    build_effective_vars,
    build_model_inputs,
)
from sqlbuild.compiler.compile._helpers.attachment.declaration_scope import build_declaration_scope
from sqlbuild.compiler.compile._helpers.diagnostics.collector import (
    with_collected_compile_diagnostics,
)
from sqlbuild.compiler.compile._helpers.macro_bridge.call_store import (
    target_context_with_macro_call_store,
)
from sqlbuild.compiler.compile._helpers.render.context_templates import resolve_run_id
from sqlbuild.compiler.compile._helpers.render.declarations import (
    build_public_declaration_indexes,
    build_public_model_schema_index,
)
from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile.models import (
    CompileAdapterContext,
    CompilerDiagnostic,
    CompileSqlScenarioInput,
    CompileSqlTestInput,
    DeclarationResolutionContext,
    DeclarationScopeBuild,
    LoadedMacro,
    MacroContext,
    ModelInputBuildContext,
    ModelInputScopeBuild,
)
from sqlbuild.compiler.compile.types import (
    AuditInput,
    CompileInputsView,
    FunctionInput,
    ModelInput,
    SeedInput,
    SourceInput,
)
from sqlbuild.compiler.compiled_project.main._attach_checks import attach_checks
from sqlbuild.compiler.compiled_project.main._attach_resources import attach_resources
from sqlbuild.compiler.compiled_project.main._compile_inputs_view import compile_inputs_view
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredProjectInputs,
    EnumDeclaration,
    ModelSchemaDeclaration,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.models import SettingsConfig, TargetConfig


@with_collected_compile_diagnostics
def build_compile_inputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter_context: CompileAdapterContext,
    selected_target: str | None = None,
    cli_vars: dict[str, object] | None = None,
    run_id: str | None = None,
    no_sql_validation: bool = False,
    defer_model_sql_validation: bool = False,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    resolved_connection: dict[str, object] | None = None,
    no_cache: bool = False,
) -> CompileInputsView:
    """Attach discovered metadata into the first compile input snapshot."""

    effective_target_name: str | None
    effective_target: TargetConfig | None
    compile_cache_dir: Path | None
    effective_target_name, effective_target, compile_cache_dir = (
        target_context_with_macro_call_store(
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
            no_cache=no_cache,
        )
    )

    effective_vars: dict[str, object] = build_effective_vars(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_config=effective_target,
        cli_vars={} if cli_vars is None else cli_vars,
    )
    effective_settings: SettingsConfig = build_effective_settings(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    macro_context: MacroContext = MacroContext(
        adapter_name=resolve_effective_adapter_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
        ),
        sql_analysis_enabled=effective_settings.sql_analysis,
        target_name=effective_target_name,
        vars=effective_vars,
        _value_renderer=adapter_context.value_renderer,
        _collection_rendering=adapter_context.collection_rendering,
        _enforce_explicit_references=(discovered_inputs.project_config.references.enforce_explicit),
    )
    resolved_run_id: str = resolve_run_id(selected_run_id=run_id)
    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)
    declaration_scope: DeclarationScopeBuild = build_declaration_scope(
        discovered_inputs=discovered_inputs,
        loaded_macros=loaded_macros,
        sql_lexical_syntax=adapter_context.sql_lexical_syntax,
        compile_cache_dir=compile_cache_dir,
    )
    model_context: ModelInputBuildContext = ModelInputBuildContext(
        effective_vars=effective_vars,
        effective_settings=effective_settings,
        target_config=effective_target,
        effective_target_name=effective_target_name,
        run_id=resolved_run_id,
        macro_context=macro_context,
        loaded_macros=declaration_scope.loaded_macros,
        value_renderer=adapter_context.value_renderer,
        collection_rendering=adapter_context.collection_rendering,
        sql_lexical_syntax=adapter_context.sql_lexical_syntax,
        declaration_resolver=declaration_scope.resolver,
    )
    model_build: ModelInputScopeBuild = _build_models_with_declarations(
        discovered_inputs=discovered_inputs,
        context=model_context,
        no_sql_validation=no_sql_validation,
        defer_model_sql_validation=defer_model_sql_validation,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    model_context = model_build.context
    seed_inputs: tuple[SeedInput, ...]
    sql_function_inputs: tuple[FunctionInput, ...]
    source_inputs: tuple[SourceInput, ...]
    seed_inputs, sql_function_inputs, source_inputs = attach_resources(
        discovered_inputs=discovered_inputs,
        native_project=model_build.native_project,
        settings=(
            model_context.effective_settings,
            model_context.target_config,
            model_context.macro_context.adapter_name,
        ),
        no_sql_validation=no_sql_validation,
        python_functions_inherit_default_namespace=(
            adapter_context.python_functions_inherit_default_namespace
        ),
    )
    test_inputs: tuple[CompileSqlTestInput, ...]
    scenario_inputs: tuple[CompileSqlScenarioInput, ...]
    audit_inputs: tuple[AuditInput, ...]
    diagnostics: tuple[CompilerDiagnostic, ...]
    test_inputs, scenario_inputs, audit_inputs, diagnostics = attach_checks(
        discovered_inputs=discovered_inputs,
        native_project=model_build.native_project,
        settings=(
            model_context.effective_settings,
            adapter_context.value_renderer,
            model_context.sql_lexical_syntax,
        ),
        scan_cache=declaration_scope.sql_test_scans,
        source_inputs=source_inputs,
    )
    fields: dict[str, Any] = {
        "project_config": discovered_inputs.project_config,
        "local_config": discovered_inputs.local_config,
        "discovered_inputs": discovered_inputs,
        "sql_lexical_syntax": adapter_context.sql_lexical_syntax,
        "run_id": resolved_run_id,
        "effective_target_name": effective_target_name,
        "effective_target": effective_target,
        "compile_cache_dir": compile_cache_dir,
        "effective_connection": (
            resolved_connection
            if resolved_connection is not None
            else build_effective_connection(
                project_config=discovered_inputs.project_config,
                local_config=discovered_inputs.local_config,
                target_config=effective_target,
                effective_vars=effective_vars,
            )
        ),
        "effective_settings": effective_settings,
        "no_sql_validation": no_sql_validation,
        "effective_vars": effective_vars,
        "macro_context": macro_context,
        "loaded_macros": declaration_scope.loaded_macros,
        "public_enums": model_build.declarations.enums,
        "public_constants": model_build.declarations.constants,
        "model_inputs": model_build.inputs,
        "seed_inputs": seed_inputs,
        "source_inputs": source_inputs,
        "sql_function_inputs": sql_function_inputs,
        "test_inputs": test_inputs,
        "scenario_inputs": scenario_inputs,
        "audit_inputs": audit_inputs,
        "diagnostics": diagnostics,
        "external_sql_reference_resolver": external_sql_reference_resolver,
        "scope_index": declaration_scope.index,
        "declaration_scope": declaration_scope,
    }
    return compile_inputs_view(fields=fields, native_project=model_build.native_project)


def _build_models_with_declarations(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool,
    defer_model_sql_validation: bool,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
) -> ModelInputScopeBuild:
    public_enums: dict[str, EnumDeclaration]
    public_constants: dict[str, ConstantDeclaration]
    public_enums, public_constants = build_public_declaration_indexes(
        discovered_inputs=discovered_inputs
    )
    public_model_schemas: dict[str, ModelSchemaDeclaration] = build_public_model_schema_index(
        discovered_inputs=discovered_inputs
    )
    declarations: DeclarationResolutionContext = DeclarationResolutionContext(
        enums=public_enums,
        constants=public_constants,
    )
    native_project: _native.NativeCompiledProject = _native.NativeCompiledProject()
    model_inputs: tuple[ModelInput, ...] = build_model_inputs(
        discovered_inputs=discovered_inputs,
        context=replace(
            context,
            public_enums=public_enums,
            public_constants=public_constants,
            public_model_schemas=public_model_schemas,
        ),
        no_sql_validation=no_sql_validation,
        defer_model_sql_validation=defer_model_sql_validation,
        external_sql_reference_resolver=external_sql_reference_resolver,
        native_project=native_project,
    )
    return ModelInputScopeBuild(
        inputs=model_inputs,
        native_project=native_project,
        declarations=declarations,
        context=replace(
            context,
            public_enums=declarations.enums,
            public_constants=declarations.constants,
        ),
    )
