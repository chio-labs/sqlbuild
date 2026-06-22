"""Build the first attached compile input snapshot from discovered inputs."""

from __future__ import annotations

from sqlbuild.compiler.auditing.main.builtins import build_builtin_audit_resolution
from sqlbuild.compiler.compile.helpers.attachment.core import (
    build_audit_inputs,
    build_effective_connection,
    build_effective_settings,
    build_effective_vars,
    build_model_inputs,
    build_scenario_inputs,
    build_seed_inputs,
    build_source_inputs,
    build_sql_function_inputs,
    build_test_inputs,
    index_generic_audit_definitions,
    resolve_run_id,
)
from sqlbuild.compiler.compile.helpers.render.macros import load_project_macros
from sqlbuild.compiler.compile.models.core import (
    CompileAuditInput,
    CompileModelInput,
    CompileProjectInputs,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlFunctionInput,
    CompileSqlScenarioInput,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.compile.models.sql_tests import CompileSqlTestInput
from sqlbuild.compiler.diagnostics.models import CompilerDiagnostic
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditBlock,
    DiscoveredAuditFile,
    DiscoveredProjectInputs,
)
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.spec.models.project import (
    SettingsConfig,
    TargetConfig,
    resolve_effective_adapter_name,
)
from sqlbuild.spec.models.targets import (
    resolve_target_config,
    resolve_target_name,
)


def build_compile_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    selected_target: str | None = None,
    cli_vars: dict[str, object] | None = None,
    run_id: str | None = None,
    no_sql_validation: bool = False,
    defer_model_sql_validation: bool = False,
    python_functions_inherit_default_namespace: bool = True,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> CompileProjectInputs:
    """Attach discovered metadata into the first compile input snapshot."""

    effective_target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=selected_target,
    )
    effective_target: TargetConfig | None = None
    if effective_target_name is not None:
        effective_target = resolve_target_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_name=effective_target_name,
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
    model_inputs: tuple[CompileModelInput, ...] = build_model_inputs(
        discovered_inputs,
        effective_vars=effective_vars,
        effective_settings=effective_settings,
        target_config=effective_target,
        effective_target_name=effective_target_name,
        run_id=resolved_run_id,
        macro_context=macro_context,
        no_sql_validation=no_sql_validation,
        defer_model_sql_validation=defer_model_sql_validation,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    seed_inputs: tuple[CompileSeedInput, ...] = build_seed_inputs(discovered_inputs)
    sql_function_inputs: tuple[CompileSqlFunctionInput, ...] = build_sql_function_inputs(
        discovered_inputs,
        effective_vars=effective_vars,
        effective_settings=effective_settings,
        target_config=effective_target,
        adapter_name=macro_context.adapter_name,
        macro_context=macro_context,
        no_sql_validation=no_sql_validation,
        python_functions_inherit_default_namespace=(python_functions_inherit_default_namespace),
    )
    source_inputs: tuple[CompileSourceInput, ...] = build_source_inputs(
        discovered_inputs,
        effective_vars=effective_vars,
        effective_settings=effective_settings,
        macro_context=macro_context,
        no_sql_validation=no_sql_validation,
    )
    test_inputs: tuple[CompileSqlTestInput, ...] = build_test_inputs(
        discovered_inputs,
        effective_vars=effective_vars,
        macro_context=macro_context,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    scenario_inputs: tuple[CompileSqlScenarioInput, ...] = build_scenario_inputs(
        discovered_inputs,
        effective_vars=effective_vars,
        macro_context=macro_context,
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
    audit_inputs: tuple[CompileAuditInput, ...] = build_audit_inputs(
        discovered_inputs,
        effective_settings=effective_settings,
        model_inputs=model_inputs,
        source_inputs=source_inputs,
        effective_vars=effective_vars,
        macro_context=macro_context,
        generic_audit_definitions=generic_audit_definitions,
    )
    return CompileProjectInputs(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        discovered_inputs=discovered_inputs,
        run_id=resolved_run_id,
        effective_target_name=effective_target_name,
        effective_target=effective_target,
        effective_connection=build_effective_connection(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_config=effective_target,
            effective_vars=effective_vars,
        ),
        effective_settings=effective_settings,
        effective_vars=effective_vars,
        loaded_macros=loaded_macros,
        model_inputs=model_inputs,
        seed_inputs=seed_inputs,
        source_inputs=source_inputs,
        sql_function_inputs=sql_function_inputs,
        test_inputs=test_inputs,
        scenario_inputs=scenario_inputs,
        audit_inputs=audit_inputs,
        diagnostics=diagnostics,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
