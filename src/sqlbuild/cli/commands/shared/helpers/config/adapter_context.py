"""Shared adapter and connection-context resolution for CLI commands."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.shared.helpers.config.adapters import resolve_adapter
from sqlbuild.cli.commands.shared.helpers.connection.core import (
    resolve_project_connection_config,
)
from sqlbuild.cli.commands.shared.models import AdapterConnectionContext
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import resolve_effective_adapter_name


def resolve_adapter_connection_context(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    effective_project_dir: Path,
    selected_target: str | None,
    cli_vars: dict[str, object] | None,
) -> AdapterConnectionContext:
    """Resolve the effective adapter and project connection configuration."""

    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(
        adapter_name=adapter_name,
        project_dir=effective_project_dir,
    )
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        selected_target=selected_target,
        cli_vars=cli_vars,
    )
    return AdapterConnectionContext(
        adapter_name=adapter_name,
        adapter=adapter,
        connection_config=connection_config,
    )
