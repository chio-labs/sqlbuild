"""Offline declaration-scope inspection command."""

from sqlbuild.cli.commands._helpers.scope.command import run_scope_command
from sqlbuild.cli.commands.models import ScopeCommandRequest


def run_scope(*, request: ScopeCommandRequest) -> int:
    """Run one offline scope inspection."""

    return run_scope_command(request=request)
