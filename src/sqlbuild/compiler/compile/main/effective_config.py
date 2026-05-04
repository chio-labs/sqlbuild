"""Effective project config helpers for compile and CLI entrypoints."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.attachment import (
    build_effective_connection,
    build_effective_vars,
    resolve_environment_config,
    resolve_environment_name,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import EnvironmentConfig


def build_effective_connection_config(
    *, discovered_inputs: DiscoveredProjectInputs, selected_environment: str | None = None
) -> dict[str, object]:
    """Build the effective project connection config without compiling resources."""

    environment_name: str | None = resolve_environment_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_environment=selected_environment,
    )
    environment_config: EnvironmentConfig | None = None
    if environment_name is not None:
        environment_config = resolve_environment_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            environment_name=environment_name,
        )
    effective_vars: dict[str, str] = build_effective_vars(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        environment_config=environment_config,
        cli_vars={},
    )
    return build_effective_connection(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        environment_config=environment_config,
        effective_vars=effective_vars,
    )
