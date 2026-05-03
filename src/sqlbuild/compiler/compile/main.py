"""Build the first attached compile input snapshot from discovered inputs."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.attachment import (
    build_audit_inputs,
    build_effective_connection,
    build_effective_vars,
    build_model_inputs,
    build_seed_inputs,
    build_source_inputs,
    build_test_inputs,
    resolve_environment_name,
    resolve_run_id,
)
from sqlbuild.compiler.compile.models import (
    CompileAuditInput,
    CompileModelInput,
    CompileProjectInputs,
    CompileSeedInput,
    CompileSourceInput,
    CompileSqlTestInput,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import EnvironmentConfig


def build_compile_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    selected_environment: str | None = None,
    cli_vars: dict[str, str] | None = None,
    run_id: str | None = None,
) -> CompileProjectInputs:
    """Attach discovered metadata into the first compile input snapshot."""

    effective_environment_name: str | None = resolve_environment_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_environment=selected_environment,
    )
    effective_environment: EnvironmentConfig | None = None
    if effective_environment_name is not None:
        effective_environment = discovered_inputs.project_config.environments[
            effective_environment_name
        ]

    effective_vars: dict[str, str] = build_effective_vars(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        environment_config=effective_environment,
        cli_vars={} if cli_vars is None else cli_vars,
    )
    resolved_run_id: str = resolve_run_id(selected_run_id=run_id)

    model_inputs: tuple[CompileModelInput, ...] = build_model_inputs(
        discovered_inputs,
        effective_vars=effective_vars,
        environment_config=effective_environment,
        effective_environment_name=effective_environment_name,
        run_id=resolved_run_id,
    )
    seed_inputs: tuple[CompileSeedInput, ...] = build_seed_inputs(discovered_inputs)
    source_inputs: tuple[CompileSourceInput, ...] = build_source_inputs(discovered_inputs)
    test_inputs: tuple[CompileSqlTestInput, ...] = build_test_inputs(discovered_inputs)
    audit_inputs: tuple[CompileAuditInput, ...] = build_audit_inputs(
        discovered_inputs,
        model_inputs=model_inputs,
        source_inputs=source_inputs,
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
            environment_config=effective_environment,
            effective_vars=effective_vars,
        ),
        effective_vars=effective_vars,
        model_inputs=model_inputs,
        seed_inputs=seed_inputs,
        source_inputs=source_inputs,
        test_inputs=test_inputs,
        audit_inputs=audit_inputs,
    )
