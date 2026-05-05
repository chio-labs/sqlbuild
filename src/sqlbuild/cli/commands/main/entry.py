"""CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.diff.validation import parse_diff_environment_range
from sqlbuild.cli.commands.main.helpers.entry.models import CliEntrypointHandlers, CliNamespace
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.parsers import (
    add_cursor_override_args,
    add_execution_args,
    add_select_args,
)
from sqlbuild.cli.commands.main.shared.types import CliCommand
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.diagnostics.main.configure import configure_diagnostics
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

    diff_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.DIFF)
    diff_parser.add_argument("environment_range", metavar="FROM:TO")
    diff_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    diff_parser.add_argument("--full", action="store_true", default=False)
    diff_parser.add_argument("--schema-only", action="store_true", default=False)
    diff_parser.add_argument("--bounded", default=None)
    diff_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    diff_parser.add_argument("--max-column-examples", type=int, default=None)
    diff_parser.add_argument("--max-row-only-examples", type=int, default=None)
    add_select_args(diff_parser)
    debug_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.DEBUG)
    debug_parser.add_argument("--json", action="store_true", default=False)
    debug_parser.add_argument("--no-connection", action="store_true", default=False)
    query_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.QUERY)
    query_parser.add_argument("query_sql", nargs="?", metavar="sql")
    query_parser.add_argument(
        "--format",
        dest="query_format",
        choices=("long", "table", "json", "csv"),
        default="long",
    )
    query_parser.add_argument("--limit", dest="query_limit", type=int, default=20)
    query_parser.add_argument(
        "--no-limit", dest="query_no_limit", action="store_true", default=False
    )
    lineage_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.LINEAGE)
    lineage_parser.add_argument("lineage_target", nargs="?", metavar="target")
    lineage_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    lineage_parser.add_argument(
        "--format",
        dest="lineage_format",
        choices=("tree", "json", "list"),
        default="tree",
    )
    lineage_parser.add_argument(
        "--direction",
        dest="lineage_direction",
        choices=("upstream", "downstream", "both"),
        default="upstream",
    )
    lineage_parser.add_argument("--depth", dest="lineage_depth", default="all")
    add_select_args(lineage_parser)
    subparsers.add_parser(CliCommand.CLEAN)
    janitor_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.JANITOR)
    janitor_parser.add_argument("--auto-approve", action="store_true", default=False)
    janitor_parser.add_argument("--retention-days", type=int, default=None)
    subparsers.add_parser(CliCommand.INIT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entrypoint."""

    from sqlbuild.cli.commands.main.audit import run_audit
    from sqlbuild.cli.commands.main.build import run_build
    from sqlbuild.cli.commands.main.clone import run_clone
    from sqlbuild.cli.commands.main.compile import run_compile
    from sqlbuild.cli.commands.main.debug import run_debug
    from sqlbuild.cli.commands.main.diff import run_diff
    from sqlbuild.cli.commands.main.janitor import run_janitor
    from sqlbuild.cli.commands.main.lineage import run_lineage
    from sqlbuild.cli.commands.main.plan import run_plan
    from sqlbuild.cli.commands.main.query import run_query
    from sqlbuild.cli.commands.main.run import run_run
    from sqlbuild.cli.commands.main.seed import run_seed
    from sqlbuild.cli.commands.main.test import run_test

    handlers: CliEntrypointHandlers = CliEntrypointHandlers(
        run_compile=run_compile,
        run_plan=run_plan,
        run_build=run_build,
        run_run=run_run,
        run_test=run_test,
        run_audit=run_audit,
        run_seed=run_seed,
        run_clone=run_clone,
        run_diff=run_diff,
        run_query=run_query,
        run_debug=run_debug,
        run_lineage=run_lineage,
        run_janitor=run_janitor,
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
        if args.command == CliCommand.LINEAGE:
            return handlers.run_lineage(
                project_dir,
                args.no_sql_validation,
                args.lineage_target,
                args.lineage_format,
                args.lineage_direction,
                args.lineage_depth,
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
        if args.command == CliCommand.DIFF:
            from_environment: str
            to_environment: str
            from_environment, to_environment = parse_diff_environment_range(args.environment_range)
            return handlers.run_diff(
                project_dir,
                args.no_color,
                args.no_sql_validation,
                from_environment,
                to_environment,
                args.full,
                args.schema_only,
                args.bounded,
                args.max_column_examples,
                args.max_row_only_examples,
                tuple(args.select),
                tuple(args.exclude),
                args.verbose,
            )
        if args.command == CliCommand.QUERY:
            query_limit: int | None = None if args.query_no_limit else args.query_limit
            return handlers.run_query(
                project_dir,
                args.query_sql,
                args.query_format,
                query_limit,
            )
        if args.command == CliCommand.DEBUG:
            return handlers.run_debug(
                project_dir,
                args.no_color,
                args.no_connection,
                args.json,
            )
        if args.command == CliCommand.JANITOR:
            return handlers.run_janitor(
                project_dir,
                args.no_color,
                args.auto_approve,
                args.retention_days,
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
