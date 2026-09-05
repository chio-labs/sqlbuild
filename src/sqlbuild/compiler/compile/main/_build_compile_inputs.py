"""Build the first attached compile input snapshot from discovered inputs."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.auditing.main._builtins import build_builtin_audit_resolution
from sqlbuild.compiler.compile._helpers.attachment.audits import (
    build_audit_inputs,
    index_generic_audit_definitions,
)
from sqlbuild.compiler.compile._helpers.attachment.core import (
    build_effective_connection,
    build_effective_settings,
    build_effective_vars,
    build_model_inputs,
    build_seed_inputs,
    resolve_run_id,
)
from sqlbuild.compiler.compile._helpers.attachment.declaration_scope import build_declaration_scope
from sqlbuild.compiler.compile._helpers.attachment.functions import build_sql_function_inputs
from sqlbuild.compiler.compile._helpers.attachment.references import (
    validate_table_function_call_arities,
)
from sqlbuild.compiler.compile._helpers.attachment.sources import build_source_inputs
from sqlbuild.compiler.compile._helpers.attachment.sql_tests import (
    build_scenario_inputs,
    build_test_inputs,
)
from sqlbuild.compiler.compile._helpers.attachment.target import build_compile_target_context
from sqlbuild.compiler.compile._helpers.audit_factories.core import (
    build_audit_factory_orphan_diagnostics,
)
from sqlbuild.compiler.compile._helpers.config.deprecation import build_cursor_alias_diagnostics
from sqlbuild.compiler.compile._helpers.render.declarations import (
    build_public_declaration_indexes,
    build_public_model_schema_index,
)
from sqlbuild.compiler.compile._helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile.models import (
    CompileAdapterContext,
    CompileAuditInput,
    CompileModelInput,
    CompileProjectInputs,
    CompilerDiagnostic,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlFunctionInput,
    CompileSqlScenarioInput,
    CompileSqlTestInput,
    DeclarationExpansionContext,
    DeclarationResolutionContext,
    DeclarationScopeBuild,
    LoadedMacro,
    MacroContext,
    ModelInputBuildContext,
    ModelInputScopeBuild,
)
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredProjectInputs,
    EnumDeclaration,
    ModelSchemaDeclaration,
)
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver
from sqlbuild.spec.contracts.main.resolve_effective_adapter_name import (
    resolve_effective_adapter_name,
)
from sqlbuild.spec.contracts.models import SettingsConfig, TargetConfig


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
) -> CompileProjectInputs:
    """Attach discovered metadata into the first compile input snapshot."""

    effective_target_name: str | None
    effective_target: TargetConfig | None
    compile_cache_dir: Path | None
    effective_target_name, effective_target, compile_cache_dir = build_compile_target_context(
        discovered_inputs=discovered_inputs,
        selected_target=selected_target,
        no_cache=no_cache,
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
    )
    resolved_run_id: str = resolve_run_id(selected_run_id=run_id)
    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)
    declaration_scope: DeclarationScopeBuild = build_declaration_scope(
        discovered_inputs=discovered_inputs, loaded_macros=loaded_macros
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
        declaration_resolver=declaration_scope.resolver,
    )
    model_build: ModelInputScopeBuild = _build_models_with_declarations(
        discovered_inputs=discovered_inputs,
        context=model_context,
        no_sql_validation=no_sql_validation,
        defer_model_sql_validation=defer_model_sql_validation,
        external_sql_reference_resolver=external_sql_reference_resolver,
        reference_cache_dir=compile_cache_dir,
    )
    model_context = model_build.context
    seed_inputs: tuple[CompileSeedInput, ...] = build_seed_inputs(discovered_inputs)
    sql_function_inputs: tuple[CompileSqlFunctionInput, ...] = _build_sql_functions(
        discovered_inputs=discovered_inputs,
        context=model_context,
        declaration_expansion=model_context.declaration_expansion,
        model_inputs=model_build.inputs,
        no_sql_validation=no_sql_validation,
        python_functions_inherit_default_namespace=(
            adapter_context.python_functions_inherit_default_namespace
        ),
    )
    source_inputs: tuple[CompileSourceInput, ...] = build_source_inputs(
        discovered_inputs=discovered_inputs,
        effective_vars=effective_vars,
        effective_settings=effective_settings,
        macro_context=macro_context,
        loaded_macros=declaration_scope.loaded_macros,
        declaration_expansion=model_context.declaration_expansion,
        no_sql_validation=no_sql_validation,
    )
    test_inputs: tuple[CompileSqlTestInput, ...] = build_test_inputs(
        discovered_inputs=discovered_inputs,
        effective_vars=effective_vars,
        macro_context=macro_context,
        loaded_macros=declaration_scope.loaded_macros,
        declaration_expansion=model_context.declaration_expansion,
        external_sql_reference_resolver=external_sql_reference_resolver,
        sql_function_inputs=sql_function_inputs,
    )
    scenario_inputs: tuple[CompileSqlScenarioInput, ...] = build_scenario_inputs(
        discovered_inputs=discovered_inputs,
        effective_vars=effective_vars,
        macro_context=macro_context,
        loaded_macros=declaration_scope.loaded_macros,
        declaration_expansion=model_context.declaration_expansion,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    project_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]] = (
        index_generic_audit_definitions(discovered_inputs.audit_files)
    )
    generic_audit_definitions: dict[str, tuple[DiscoveredAuditFile, DiscoveredAuditBlock]]
    diagnostics: tuple[CompilerDiagnostic, ...]
    generic_audit_definitions, diagnostics = build_builtin_audit_resolution(
        project_audit_definitions
    )
    diagnostics = (*diagnostics, *model_build.diagnostics)
    audit_inputs: tuple[CompileAuditInput, ...] = build_audit_inputs(
        discovered_inputs=discovered_inputs,
        effective_settings=effective_settings,
        model_inputs=model_build.inputs,
        source_inputs=source_inputs,
        effective_vars=effective_vars,
        macro_context=macro_context,
        loaded_macros=declaration_scope.loaded_macros,
        declaration_expansion=model_context.declaration_expansion,
        generic_audit_definitions=generic_audit_definitions,
    )
    return CompileProjectInputs(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        discovered_inputs=discovered_inputs,
        run_id=resolved_run_id,
        effective_target_name=effective_target_name,
        effective_target=effective_target,
        compile_cache_dir=compile_cache_dir,
        effective_connection=(
            resolved_connection
            if resolved_connection is not None
            else build_effective_connection(
                project_config=discovered_inputs.project_config,
                local_config=discovered_inputs.local_config,
                target_config=effective_target,
                effective_vars=effective_vars,
            )
        ),
        effective_settings=effective_settings,
        effective_vars=effective_vars,
        loaded_macros=declaration_scope.loaded_macros,
        public_enums=model_build.declarations.enums,
        public_constants=model_build.declarations.constants,
        model_inputs=model_build.inputs,
        seed_inputs=seed_inputs,
        source_inputs=source_inputs,
        sql_function_inputs=sql_function_inputs,
        test_inputs=test_inputs,
        scenario_inputs=scenario_inputs,
        audit_inputs=audit_inputs,
        diagnostics=diagnostics,
        external_sql_reference_resolver=external_sql_reference_resolver,
        scope_index=declaration_scope.index,
    )


def _build_sql_functions(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    declaration_expansion: DeclarationExpansionContext,
    model_inputs: tuple[CompileModelInput, ...],
    no_sql_validation: bool,
    python_functions_inherit_default_namespace: bool,
) -> tuple[CompileSqlFunctionInput, ...]:
    sql_function_inputs: tuple[CompileSqlFunctionInput, ...] = build_sql_function_inputs(
        discovered_inputs=discovered_inputs,
        effective_vars=context.effective_vars,
        effective_settings=context.effective_settings,
        target_config=context.target_config,
        adapter_name=context.macro_context.adapter_name,
        macro_context=context.macro_context,
        loaded_macros=context.loaded_macros,
        declaration_expansion=declaration_expansion,
        no_sql_validation=no_sql_validation,
        python_functions_inherit_default_namespace=python_functions_inherit_default_namespace,
    )
    validate_table_function_call_arities(
        model_inputs=model_inputs,
        sql_function_inputs=sql_function_inputs,
    )
    return sql_function_inputs


def _build_models_with_declarations(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    context: ModelInputBuildContext,
    no_sql_validation: bool,
    defer_model_sql_validation: bool,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None,
    reference_cache_dir: Path | None,
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
    model_inputs: tuple[CompileModelInput, ...] = build_model_inputs(
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
        reference_cache_dir=reference_cache_dir,
    )
    return ModelInputScopeBuild(
        inputs=model_inputs,
        declarations=declarations,
        context=replace(
            context,
            public_enums=declarations.enums,
            public_constants=declarations.constants,
        ),
        diagnostics=(
            *build_cursor_alias_diagnostics(model_inputs=model_inputs),
            *build_audit_factory_orphan_diagnostics(discovered_inputs=discovered_inputs),
        ),
    )
