"""CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlbuild.cli.commands.main.entry.models import CliEntrypointHandlers, CliNamespace
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.parsers import (
    add_cursor_override_args,
    add_execution_args,
    add_select_args,
)
from sqlbuild.cli.commands.main.shared.types import CliCommand
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.diagnostics.main import configure_diagnostics
from sqlbuild.shared.helpers.colors import supports_color


def _build_parser() -> argparse.ArgumentParser:
    """Build the root CLI parser."""

    parser: argparse.ArgumentParser = argparse.ArgumentParser(prog="sqb")
    parser.add_argument("--project-dir", default=None)
    parser.add_argument("--no-color", action="store_true", default=False)
    parser.add_argument("--debug", action="store_true", default=False)

    subparsers: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(
        dest="command"
    )
    compile_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.COMPILE)
    compile_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    compile_parser.add_argument("--defer-to", default=None)
    compile_parser.add_argument("--json", action="store_true", default=False)

    plan_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.PLAN)
    plan_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    plan_parser.add_argument("--defer-to", default=None)
    plan_parser.add_argument("--json", action="store_true", default=False)
    plan_parser.add_argument("--full-refresh", action="store_true", default=False)
    add_cursor_override_args(plan_parser)
    add_select_args(plan_parser)

    build_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.BUILD)
    build_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    build_parser.add_argument("--defer-to", default=None)
    add_cursor_override_args(build_parser)
    add_execution_args(build_parser)
    add_select_args(build_parser)

    run_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.RUN)
    run_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    run_parser.add_argument("--defer-to", default=None)
    add_cursor_override_args(run_parser)
    add_execution_args(run_parser)
    add_select_args(run_parser)

    test_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.TEST)
    test_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    add_select_args(test_parser)

    audit_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.AUDIT)
    audit_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    audit_parser.add_argument("--defer-to", default=None)
    add_select_args(audit_parser)

    seed_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.SEED)
    add_select_args(seed_parser)

    clone_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.CLONE)
    clone_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    clone_parser.add_argument("--from", dest="from_environment", required=True)
    clone_parser.add_argument("--to", dest="to_environment", required=True)
    clone_parser.add_argument("--hard-copy", action="store_true", default=False)
    add_select_args(clone_parser)

    subparsers.add_parser(CliCommand.DIFF)
    subparsers.add_parser(CliCommand.CLEAN)
    subparsers.add_parser(CliCommand.JANITOR)
    subparsers.add_parser(CliCommand.INIT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entrypoint."""

    from sqlbuild.cli.commands.main.audit.main import run_audit
    from sqlbuild.cli.commands.main.build.main import run_build
    from sqlbuild.cli.commands.main.clone.main import run_clone
    from sqlbuild.cli.commands.main.compile.main import run_compile
    from sqlbuild.cli.commands.main.plan.main import run_plan
    from sqlbuild.cli.commands.main.run.main import run_run
    from sqlbuild.cli.commands.main.seed.main import run_seed
    from sqlbuild.cli.commands.main.test.main import run_test

    handlers: CliEntrypointHandlers = CliEntrypointHandlers(
        run_compile=run_compile,
        run_plan=run_plan,
        run_build=run_build,
        run_run=run_run,
        run_test=run_test,
        run_audit=run_audit,
        run_seed=run_seed,
        run_clone=run_clone,
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
        effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
        if args.command is not None:
            configure_diagnostics(
                target_dir=effective_project_dir / "target",
                debug=args.debug,
                use_color=(not args.no_color) and supports_color(),
            )
            logging.getLogger("sqlbuild.cli").debug(
                "command=%s project_dir=%s", args.command, effective_project_dir
            )
        if args.command == CliCommand.COMPILE:
            return handlers.run_compile(
                project_dir, args.no_sql_validation, args.defer_to, args.json
            )
        if args.command == CliCommand.PLAN:
            cursor_overrides: CursorOverrides = CursorOverrides(
                start_ts=args.start_cursor_ts,
                end_ts=args.end_cursor_ts,
                start_int=args.start_cursor_int,
                end_int=args.end_cursor_int,
            )
            return handlers.run_plan(
                project_dir,
                args.no_sql_validation,
                args.defer_to,
                cursor_overrides,
                args.json,
                args.full_refresh,
                args.no_color,
                tuple(args.select),
                tuple(args.exclude),
            )
        if args.command == CliCommand.BUILD:
            cursor_overrides = CursorOverrides(
                start_ts=args.start_cursor_ts,
                end_ts=args.end_cursor_ts,
                start_int=args.start_cursor_int,
                end_int=args.end_cursor_int,
            )
            return handlers.run_build(
                project_dir,
                args.no_sql_validation,
                args.defer_to,
                cursor_overrides,
                args.no_color,
                args.fail_fast,
                args.full_refresh,
                args.concurrency,
                tuple(args.select),
                tuple(args.exclude),
                args.verbose,
                args.debug,
            )
        if args.command == CliCommand.RUN:
            cursor_overrides = CursorOverrides(
                start_ts=args.start_cursor_ts,
                end_ts=args.end_cursor_ts,
                start_int=args.start_cursor_int,
                end_int=args.end_cursor_int,
            )
            return handlers.run_run(
                project_dir,
                args.no_sql_validation,
                args.defer_to,
                cursor_overrides,
                args.no_color,
                args.fail_fast,
                args.full_refresh,
                args.concurrency,
                tuple(args.select),
                tuple(args.exclude),
                args.verbose,
                args.debug,
            )
        if args.command == CliCommand.TEST:
            return handlers.run_test(
                project_dir,
                args.no_sql_validation,
                args.no_color,
                tuple(args.select),
                tuple(args.exclude),
            )
        if args.command == CliCommand.AUDIT:
            return handlers.run_audit(
                project_dir,
                args.no_sql_validation,
                args.defer_to,
                args.no_color,
                tuple(args.select),
                tuple(args.exclude),
            )
        if args.command == CliCommand.SEED:
            return handlers.run_seed(
                project_dir,
                args.no_color,
                tuple(args.select),
                tuple(args.exclude),
            )
        if args.command == CliCommand.CLONE:
            if args.from_environment is None or args.to_environment is None:
                raise CliUserError("clone requires --from and --to")
            return handlers.run_clone(
                project_dir,
                args.no_color,
                args.no_sql_validation,
                args.from_environment,
                args.to_environment,
                args.hard_copy,
                tuple(args.select),
                tuple(args.exclude),
            )
        return 0
    except CliUserError as error:
        logging.getLogger("sqlbuild.cli").exception("cli user error")
        print(str(error), file=sys.stderr)
        return 1
    except (DiscoveryError, ValueError) as error:
        logging.getLogger("sqlbuild.cli").exception("command failed")
        print(str(error), file=sys.stderr)
        return 1
