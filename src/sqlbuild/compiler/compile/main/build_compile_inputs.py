"""Build the first attached compile input snapshot from discovered inputs."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.attachment import (
    build_audit_inputs,
    build_effective_connection,
    build_effective_settings,
    build_effective_vars,
    build_model_inputs,
    build_seed_inputs,
    build_source_inputs,
    build_sql_function_inputs,
    build_test_inputs,
    resolve_environment_config,
    resolve_environment_name,
    resolve_run_id,
)
from sqlbuild.compiler.compile.helpers.macros import load_project_macros
from sqlbuild.compiler.compile.models import (
    CompileAuditInput,
    CompileModelInput,
    CompileProjectInputs,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlFunctionInput,
    CompileSqlTestInput,
    LoadedMacro,
    MacroContext,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import (
    EnvironmentConfig,
    SettingsConfig,
    resolve_effective_adapter_name,
)


def build_compile_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    selected_environment: str | None = None,
    cli_vars: dict[str, str] | None = None,
    run_id: str | None = None,
    no_sql_validation: bool = False,
    python_functions_inherit_default_namespace: bool = True,
) -> CompileProjectInputs:
    """Attach discovered metadata into the first compile input snapshot."""

    effective_environment_name: str | None = resolve_environment_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_environment=selected_environment,
    )
    effective_environment: EnvironmentConfig | None = None
    if effective_environment_name is not None:
        effective_environment = resolve_environment_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            environment_name=effective_environment_name,
        )

    effective_vars: dict[str, str] = build_effective_vars(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        environment_config=effective_environment,
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
        sqlglot_enabled=effective_settings.sqlglot,
        environment_name=effective_environment_name,
        vars=effective_vars,
    )
    resolved_run_id: str = resolve_run_id(selected_run_id=run_id)
    loaded_macros: dict[str, LoadedMacro] = load_project_macros(discovered_inputs.macro_files)

    model_inputs: tuple[CompileModelInput, ...] = build_model_inputs(
        discovered_inputs,
        effective_vars=effective_vars,
        effective_settings=effective_settings,
        environment_config=effective_environment,
        effective_environment_name=effective_environment_name,
        run_id=resolved_run_id,
        macro_context=macro_context,
        no_sql_validation=no_sql_validation,
    )
    seed_inputs: tuple[CompileSeedInput, ...] = build_seed_inputs(discovered_inputs)
    sql_function_inputs: tuple[CompileSqlFunctionInput, ...] = build_sql_function_inputs(
        discovered_inputs,
        effective_vars=effective_vars,
        effective_settings=effective_settings,
        environment_config=effective_environment,
        adapter_name=macro_context.adapter_name,
        macro_context=macro_context,
        no_sql_validation=no_sql_validation,
        python_functions_inherit_default_namespace=(python_functions_inherit_default_namespace),
    )
    source_inputs: tuple[CompileSourceInput, ...] = build_source_inputs(
        discovered_inputs,
        effective_settings=effective_settings,
        no_sql_validation=no_sql_validation,
    )
    test_inputs: tuple[CompileSqlTestInput, ...] = build_test_inputs(
        discovered_inputs,
        effective_vars=effective_vars,
        macro_context=macro_context,
    )
    audit_inputs: tuple[CompileAuditInput, ...] = build_audit_inputs(
        discovered_inputs,
        effective_settings=effective_settings,
        model_inputs=model_inputs,
        source_inputs=source_inputs,
        macro_context=macro_context,
    )
    return CompileProjectInputs(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        discovered_inputs=discovered_inputs,
        run_id=resolved_run_id,
        effective_environment_name=effective_environment_name,
        effective_environment=effective_environment,
        effective_connection=build_effective_connection(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            environment_config=effective_environment,
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
        audit_inputs=audit_inputs,
    )
