"""CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from sqlbuild.cli.commands._helpers.entry.dispatch import dispatch_cli_command
from sqlbuild.cli.commands._helpers.entry.errors import (
    cli_error_use_color,
    format_expected_error,
)
from sqlbuild.cli.commands._helpers.entry.lazy_handlers import build_lazy_cli_handlers
from sqlbuild.cli.commands._helpers.entry.parser import build_cli_parser
from sqlbuild.cli.commands._helpers.entry.parsing import parse_cli_invocation
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import CliEntrypointHandlers, ParsedCliInvocation
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.lint.exceptions import LintError
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.virtual.state.exceptions import StateBackendError


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entrypoint."""

    return _main_with_dependencies(argv=argv, handlers=build_lazy_cli_handlers())


def _main_with_dependencies(
    *,
    argv: Sequence[str] | None = None,
    handlers: CliEntrypointHandlers,
) -> int:
    """Run the CLI entrypoint with injected handlers for testing."""

    use_color: bool = cli_error_use_color(argv=argv, supports_color=supports_color)
    parser: argparse.ArgumentParser = build_cli_parser(use_color=use_color)
    invocation: ParsedCliInvocation = parse_cli_invocation(argv=argv, parser=parser)
    if invocation.args is None:
        return invocation.exit_code if invocation.exit_code is not None else 1
    try:
        return dispatch_cli_command(args=invocation.args, handlers=handlers)
    except SystemExit as error:
        if isinstance(error.code, int):
            return error.code
        return 1
    except (CliUserError, KataError) as error:
        logging.getLogger("sqlbuild.cli").exception("cli user error")
        print(
            format_expected_error(error=error, fallback_code="C000", use_color=use_color),
            file=sys.stderr,
        )
        return 1
    except LintError as error:
        logging.getLogger("sqlbuild.cli").exception("lint failed")
        print(
            format_expected_error(error=error, fallback_code="L001", use_color=use_color),
            file=sys.stderr,
        )
        return 1
    except (DiscoveryError, StateBackendError, ValueError) as error:
        logging.getLogger("sqlbuild.cli").exception("command failed")
        print(
            format_expected_error(error=error, fallback_code="E001", use_color=use_color),
            file=sys.stderr,
        )
        return 1
