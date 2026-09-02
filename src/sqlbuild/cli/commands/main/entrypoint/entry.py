"""CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlbuild.cli.commands._helpers.entry.errors import (
    cli_error_use_color,
    format_expected_error,
)
from sqlbuild.cli.commands._helpers.entry.lazy_handlers import build_lazy_cli_handlers
from sqlbuild.cli.commands._helpers.entry.parser import build_cli_parser
from sqlbuild.cli.commands._helpers.entry.parsing import parse_cli_invocation
from sqlbuild.cli.commands._helpers.skills.update import maintain_sqlbuild_skills
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.main.entrypoint._dispatch_with_history import dispatch_with_history
from sqlbuild.cli.commands.models import (
    CliEntrypointHandlers,
    ParsedCliInvocation,
    SkillMaintenanceResult,
)
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.kata_engine.exceptions import KataError
from sqlbuild.lint.exceptions import LintError
from sqlbuild.observability import invocation_scope
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

    with invocation_scope() as identity:
        with diagnostics_context(sqlbuild_invocation_id=identity.invocation_id):
            use_color: bool = cli_error_use_color(argv=argv, supports_color=supports_color)
            parser: argparse.ArgumentParser = build_cli_parser(use_color=use_color)
            invocation: ParsedCliInvocation = parse_cli_invocation(argv=argv, parser=parser)
            if invocation.args is None:
                return invocation.exit_code if invocation.exit_code is not None else 1
            try:
                return dispatch_with_history(args=invocation.args, handlers=handlers)
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
            finally:
                _report_skill_freshness(invocation=invocation)


def _report_skill_freshness(*, invocation: ParsedCliInvocation) -> None:
    args: CliNamespace | None = invocation.args
    if args is None or args.command in {
        CliCommand.INIT,
        CliCommand.PLAYGROUND,
        CliCommand.SKILLS,
    }:
        return
    project_dir: Path = Path(args.project_dir) if args.project_dir is not None else Path.cwd()
    try:
        result: SkillMaintenanceResult = maintain_sqlbuild_skills(project_dir=project_dir)
    except (CliUserError, OSError):
        return
    if result.message:
        print(result.message, file=sys.stderr, end="")
