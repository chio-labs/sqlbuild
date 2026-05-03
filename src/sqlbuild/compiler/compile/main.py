"""Build the first attached compile input snapshot from discovered inputs."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.attachment import (
    build_effective_connection,
    build_effective_vars,
    build_model_inputs,
    build_seed_inputs,
    build_source_inputs,
    resolve_environment_name,
)
from sqlbuild.compiler.compile.models import (
    CompileModelInput,
    CompileProjectInputs,
    CompileSeedInput,
    CompileSourceInput,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import EnvironmentConfig


def build_compile_inputs(
    discovered_inputs: DiscoveredProjectInputs,
    *,
    selected_environment: str | None = None,
    cli_vars: dict[str, str] | None = None,
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

    model_inputs: tuple[CompileModelInput, ...] = build_model_inputs(discovered_inputs)
    seed_inputs: tuple[CompileSeedInput, ...] = build_seed_inputs(discovered_inputs)
    source_inputs: tuple[CompileSourceInput, ...] = build_source_inputs(discovered_inputs)
    return CompileProjectInputs(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        discovered_inputs=discovered_inputs,
        effective_environment_name=effective_environment_name,
        effective_environment=effective_environment,
        effective_connection=build_effective_connection(
            project_config=discovered_inputs.project_config,
            environment_config=effective_environment,
        ),
        effective_vars=build_effective_vars(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            environment_config=effective_environment,
            cli_vars={} if cli_vars is None else cli_vars,
        ),
        model_inputs=model_inputs,
        seed_inputs=seed_inputs,
        source_inputs=source_inputs,
    )
