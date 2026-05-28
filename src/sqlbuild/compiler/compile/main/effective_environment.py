"""Effective environment config helpers for CLI entrypoints."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.environments import (
    resolve_environment_config,
    resolve_environment_name,
)
from sqlbuild.spec.models.project import EnvironmentConfig


def build_effective_environment_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_environment: str | None = None,
) -> EnvironmentConfig | None:
    """Build effective environment config without compiling resources."""

    environment_name: str | None = resolve_environment_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_environment=selected_environment,
    )
    if environment_name is None:
        return None
    return resolve_environment_config(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        environment_name=environment_name,
    )
