"""Shared progress reporter construction for CLI commands."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.commands.shared.helpers.progress.connection import ConnectionProgressReporter
from sqlbuild.cli.commands.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.cli.commands.shared.models import CommandProgressReporters


def build_command_progress_reporters(
    *,
    adapter_name: str,
    stream: TextIO,
    use_color: bool,
) -> CommandProgressReporters:
    """Build connection and planning progress reporters for one command."""

    return CommandProgressReporters(
        connection=ConnectionProgressReporter(
            adapter_name=adapter_name,
            stream=stream,
            use_color=use_color,
        ),
        planning=PlanningProgressReporter(
            stream=stream,
            use_color=use_color,
        ),
    )
