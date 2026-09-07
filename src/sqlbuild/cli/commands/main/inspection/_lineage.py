"""CLI lineage command entry point."""

from __future__ import annotations

from sqlbuild.cli.commands._helpers.lineage.execution import execute_lineage
from sqlbuild.cli.commands.models import LineageCommandRequest


def run_lineage(request: LineageCommandRequest) -> int:
    """Execute the lineage command."""

    return execute_lineage(request=request)
