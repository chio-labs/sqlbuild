"""Effective target config helpers for CLI entrypoints."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import TargetConfig
from sqlbuild.spec.resolution.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.resolution.main.resolve_target_name import resolve_target_name


def build_effective_target_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None = None,
) -> TargetConfig | None:
    """Build effective target config without compiling resources."""

    target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=selected_target,
    )
    if target_name is None:
        return None
    return resolve_target_config(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        target_name=target_name,
    )
