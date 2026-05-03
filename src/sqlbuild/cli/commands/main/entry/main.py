"""CLI entrypoint."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlbuild.cli.commands.main.entry.models import CliEntrypointHandlers, CliNamespace
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.types import CliCommand
from sqlbuild.compiler.discovery.exceptions import DiscoveryError


def _build_parser() -> argparse.ArgumentParser:
    """Build the root CLI parser."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="sqb")
    parser.add_argument("--project-dir", default=None)

    subparsers: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(
        dest="command"
    )
    compile_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.COMPILE)
    compile_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    compile_parser.add_argument("--defer-to", default=None)
    run_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.RUN)
    run_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    run_parser.add_argument("--defer-to", default=None)
    plan_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.PLAN)
    plan_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    plan_parser.add_argument("--defer-to", default=None)
    plan_parser.add_argument("--verbose", action="store_true", default=False)
    build_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.BUILD)
    build_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    build_parser.add_argument("--defer-to", default=None)
    subparsers.add_parser(CliCommand.TEST)
    subparsers.add_parser(CliCommand.AUDIT)
    subparsers.add_parser(CliCommand.SEED)
    subparsers.add_parser(CliCommand.CLONE)
    subparsers.add_parser(CliCommand.DIFF)
    subparsers.add_parser(CliCommand.CLEAN)
    subparsers.add_parser(CliCommand.JANITOR)
    subparsers.add_parser(CliCommand.INIT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entrypoint."""

    from sqlbuild.cli.commands.main.compile.main import run_compile
    from sqlbuild.cli.commands.main.plan.main import run_plan

    handlers: CliEntrypointHandlers = CliEntrypointHandlers(
        run_compile=run_compile, run_plan=run_plan
    )
    return _main_with_dependencies(argv=argv, handlers=handlers)


def _main_with_dependencies(
    argv: Sequence[str] | None = None,
    *,
    handlers: CliEntrypointHandlers,
) -> int:
    """Run the CLI entrypoint with injected handlers for testing."""

    parser: argparse.ArgumentParser = _build_parser()
    try:
        args: CliNamespace = CliNamespace()
        parser.parse_args(argv, namespace=args)
    except SystemExit as error:
        if isinstance(error.code, int):
            return error.code
        return 1

    try:
        project_dir: Path | None = None if args.project_dir is None else Path(args.project_dir)
        if args.command == CliCommand.COMPILE:
            return handlers.run_compile(project_dir, args.no_sql_validation, args.defer_to)
        if args.command == CliCommand.PLAN:
            return handlers.run_plan(
                project_dir, args.no_sql_validation, args.defer_to, args.verbose
            )
        return 0
    except CliUserError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (DiscoveryError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
