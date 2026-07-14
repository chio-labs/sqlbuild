"""Effective runtime config helpers for CLI entrypoints."""

from __future__ import annotations

from sqlbuild.compiler.compile.helpers.attachment.core import (
    build_effective_vars,
    resolve_run_id,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import TargetConfig
from sqlbuild.spec.resolution.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.resolution.main.resolve_target_name import resolve_target_name


def build_effective_runtime_config(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    selected_target: str | None = None,
    cli_vars: dict[str, object] | None = None,
) -> tuple[str | None, dict[str, object], str]:
    """Build environment, vars, and invocation id without compiling resources."""

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
    return target_name, effective_vars, resolve_run_id(selected_run_id=None)
