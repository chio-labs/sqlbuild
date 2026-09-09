"""Focused compiler-rule CLI entrypoint."""

from sqlbuild.cli.commands._helpers.rules.command import run_rules_command as execute_rules_command
from sqlbuild.cli.commands.models import RulesCommandRequest


def run_rules_command(request: RulesCommandRequest) -> int:
    """Execute one focused Rules command."""

    return execute_rules_command(request)
