"""CLI entrypoint."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from sqlbuild.cli.commands._helpers.entry.dispatch_errors import dispatch_and_handle_errors
from sqlbuild.cli.commands._helpers.entry.errors import cli_error_use_color
from sqlbuild.cli.commands._helpers.entry.lazy_handlers import build_lazy_cli_handlers
from sqlbuild.cli.commands._helpers.entry.parser import build_cli_parser
from sqlbuild.cli.commands._helpers.entry.parsing import parse_cli_invocation
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.main.entrypoint._dispatch_with_compute_logs import (
    dispatch_with_compute_logs,
)
from sqlbuild.cli.commands.models import (
    CliEntrypointHandlers,
    ParsedCliInvocation,
)
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.observability import invocation_scope
from sqlbuild.presentation.main.supports_color import supports_color


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entrypoint."""

    return _main_with_dependencies(argv=argv, handlers=build_lazy_cli_handlers())


def _main_with_dependencies(
    *,
    argv: Sequence[str] | None = None,
    handlers: CliEntrypointHandlers,
) -> int:
    """Run the CLI entrypoint with injected handlers for testing."""

    with invocation_scope() as identity:
        with diagnostics_context(sqlbuild_invocation_id=identity.invocation_id):
            use_color: bool = cli_error_use_color(argv=argv, supports_color=supports_color)
            parser: argparse.ArgumentParser = build_cli_parser(use_color=use_color)
            invocation: ParsedCliInvocation = parse_cli_invocation(argv=argv, parser=parser)
            if invocation.args is None:
                return invocation.exit_code if invocation.exit_code is not None else 1
            args: CliNamespace = invocation.args
            return dispatch_with_compute_logs(
                args=args,
                identity=identity,
                operation=lambda: dispatch_and_handle_errors(
                    args=args,
                    invocation=invocation,
                    handlers=handlers,
                    use_color=use_color,
                ),
            )
