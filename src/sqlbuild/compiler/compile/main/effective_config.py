"""Effective project config helpers for compile and CLI entrypoints."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.attachment import (
    build_effective_connection,
    build_effective_vars,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import TargetConfig
from sqlbuild.spec.models.targets import (
    resolve_target_config,
    resolve_target_name,
)


def build_effective_connection_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None = None,
    cli_vars: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the effective project connection config without compiling resources."""

    target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=selected_target,
    )
    target_config: TargetConfig | None = None
    if target_name is not None:
        target_config = resolve_target_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_name=target_name,
        )
    effective_vars: dict[str, object] = build_effective_vars(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_config=target_config,
        cli_vars={} if cli_vars is None else cli_vars,
    )
    return build_effective_connection(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_config=target_config,
        effective_vars=effective_vars,
    )
