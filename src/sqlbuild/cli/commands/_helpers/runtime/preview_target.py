"""Shared validation for inspection-only ``--as`` target previews."""

from __future__ import annotations

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


def validate_preview_target(
    *, discovered_inputs: DiscoveredProjectInputs, as_target: str | None, command_name: str
) -> None:
    """Fail clearly when ``--as`` names a target that is not configured."""

    if as_target is None:
        return
    configured: set[str] = set(discovered_inputs.project_config.targets) | set(
        discovered_inputs.local_config.targets
    )
    if as_target not in configured:
        raise CliUserError(
            f"unknown target '{as_target}' for {command_name} --as",
            help=f"Configured targets: {', '.join(sorted(configured)) or 'none'}.",
        )
