"""Janitor command invocation and settings phases."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.janitor_runtime.models import (
    JanitorCommandRequest,
    JanitorInvocation,
    JanitorSettings,
)
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.presentation.main.supports_color import supports_color


def resolve_janitor_invocation(*, request: JanitorCommandRequest) -> JanitorInvocation:
    """Resolve project discovery and output context for janitor."""

    effective_project_dir: Path = (
        request.project_dir if request.project_dir is not None else Path.cwd()
    )
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    return JanitorInvocation(
        effective_project_dir=effective_project_dir,
        discovered_inputs=discovered_inputs,
        use_color=not request.no_color and supports_color(),
    )


def resolve_janitor_settings(
    *, request: JanitorCommandRequest, invocation: JanitorInvocation
) -> JanitorSettings:
    """Resolve and validate effective janitor settings."""

    retention_days: int = (
        request.retention_days
        if request.retention_days is not None
        else invocation.discovered_inputs.project_config.janitor.retention_days
    )
    if retention_days < 0:
        raise CliUserError("janitor --retention-days must be >= 0", code="C501")
    direct_state_history_versions: int = (
        request.direct_state_history_versions
        if request.direct_state_history_versions is not None
        else invocation.discovered_inputs.project_config.janitor.direct_state_history_versions
    )
    if direct_state_history_versions < 0:
        raise CliUserError("janitor --direct-state-history-versions must be >= 0", code="C502")
    return JanitorSettings(
        retention_days=retention_days,
        direct_state_history_versions=direct_state_history_versions,
    )
