"""CLI mode guard helpers."""

from __future__ import annotations

from sqlbuild.cli.commands.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


def enforce_standard_mode_command_support(
    *, discovered_inputs: DiscoveredProjectInputs, command_name: str
) -> None:
    """Block commands that are not yet supported in virtual mode."""

    if discovered_inputs.project_config.settings.virtual_environments:
        raise CliUserError(
            f"{command_name} is not supported when virtual_environments = true",
            code="C241",
        )


def enforce_no_defer_to_in_virtual_mode(
    *, discovered_inputs: DiscoveredProjectInputs, command_name: str, defer_to: str | None
) -> None:
    """Block classic model-output deferral in virtual mode."""

    if defer_to is None:
        return
    if discovered_inputs.project_config.settings.virtual_environments:
        raise CliUserError(
            f"{command_name} does not support --defer-to when virtual_environments = true",
            code="C242",
        )
