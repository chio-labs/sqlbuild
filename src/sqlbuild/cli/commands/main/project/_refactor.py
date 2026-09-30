"""CLI entry for `sqb rename` and `sqb mv`."""

from sqlbuild.cli.commands._helpers.refactor.command import run_refactor_command
from sqlbuild.cli.commands.models import RefactorCommandRequest


def run_refactor(*, request: RefactorCommandRequest) -> int:
    """Run one rename or move."""

    return run_refactor_command(request=request)
