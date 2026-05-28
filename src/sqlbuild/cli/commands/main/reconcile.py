"""CLI reconcile command entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.status import TransientStatusReporter
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.helpers.colors import blue_bold, green_bold, supports_color
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
    auto_approve: bool = False,
    cli_vars: dict[str, object] | None = None,
) -> int:
    """Execute the reconcile command."""

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
    if reconcile_command == "attach" and not auto_approve:
        if model_name is None:
            raise CliUserError("reconcile attach requires --model", code="C249")
        prompt: str = f"Type 'attach {model_name}' to confirm: "
        if input(prompt).strip() != f"attach {model_name}":
            raise CliUserError("reconcile attach cancelled", code="C262")
    use_color: bool = not no_color and supports_color()
    status: TransientStatusReporter = TransientStatusReporter(
        stream=sys.stdout,
        use_color=use_color,
    )
    status.start("Reconciling virtual environment...")
    try:
        message: str = run_virtual_reconcile(
            project_dir=effective_project_dir,
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            connection_config=connection_config,
            virtual_environment_name=virtual_environment,
            command=reconcile_command,
            model_name=model_name,
            physical_relation_name=physical_relation_name,
        )
        status.complete("Reconciled virtual environment.")
    except BaseException:
        status.error("Reconcile failed.")
        raise
    print(_format_reconcile_output(message=message, use_color=use_color))
    return 0


def _format_reconcile_output(*, message: str, use_color: bool) -> str:
    title: str = green_bold("Virtual reconcile") if use_color else "Virtual reconcile"
    rendered_message: str = blue_bold(message) if use_color and "no issues" in message else message
    return "\n" + title + "\n\n" + rendered_message + "\n"
