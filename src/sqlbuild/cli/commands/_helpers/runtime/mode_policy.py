"""CLI live-mode policy checks."""

from __future__ import annotations

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs


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


def enforce_virtual_only_flags_in_virtual_mode(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    command_name: str,
    virtual_env: str | None,
    include_stale_upstreams: bool,
    changes_only: bool = False,
) -> None:
    """Block virtual-environment-only flags on standard-mode projects."""

    if discovered_inputs.project_config.settings.virtual_environments:
        return
    if virtual_env is not None:
        raise CliUserError(
            f"{command_name} does not support --virtual-env unless virtual_environments = true",
            code="C263",
        )
    if include_stale_upstreams:
        raise CliUserError(
            f"{command_name} does not support --include-stale-upstreams unless "
            "virtual_environments = true",
            code="C263",
        )
    if changes_only:
        raise CliUserError(
            f"{command_name} does not support --changes-only unless virtual_environments = true",
            code="C263",
        )
