"""Effective runtime config helpers for CLI entrypoints."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.attachment import (
    build_effective_vars,
    resolve_run_id,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.environments import (
    resolve_environment_config,
    resolve_environment_name,
)
from sqlbuild.spec.models.project import EnvironmentConfig


def build_effective_runtime_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_environment: str | None = None,
    cli_vars: dict[str, object] | None = None,
) -> tuple[str | None, dict[str, object], str]:
    """Build environment, vars, and invocation id without compiling resources."""

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
    effective_vars: dict[str, object] = build_effective_vars(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        environment_config=environment_config,
        cli_vars={} if cli_vars is None else cli_vars,
    )
    return environment_name, effective_vars, resolve_run_id(selected_run_id=None)
