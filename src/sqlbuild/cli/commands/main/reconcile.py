"""CLI reconcile command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import resolve_effective_adapter_name
from sqlbuild.spec.models.types import EnvironmentMode
from sqlbuild.virtual.reconcile.main.reconcile import run_virtual_reconcile


def run_reconcile(
    project_dir: Path | None,
    no_color: bool,
    virtual_environment: str | None,
    reconcile_command: str | None,
    model_name: str | None,
    physical_relation_name: str | None,
    cli_vars: dict[str, object] | None = None,
) -> int:
    """Execute the reconcile command."""

    del no_color
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    if discovered_inputs.project_config.environment_mode != EnvironmentMode.VIRTUAL:
        raise CliUserError("reconcile requires environment_mode = 'virtual'", code="C254")
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=effective_project_dir)
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
        cli_vars=cli_vars,
    )
    print(
        run_virtual_reconcile(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            connection_config=connection_config,
            virtual_environment_name=virtual_environment,
            command=reconcile_command,
            model_name=model_name,
            physical_relation_name=physical_relation_name,
        )
    )
    return 0
