"""CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.compile.constants import COMPILE_LINEAGE_MODE_VALUES
from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode
from sqlbuild.cli.commands.main.helpers.diff.validation import parse_diff_environment_range
from sqlbuild.cli.commands.main.helpers.entry.errors import (
    SqlbuildArgumentParser,
    build_argument_parser_class,
    cli_error_use_color,
    format_expected_error,
)
from sqlbuild.cli.commands.main.helpers.entry.models import CliEntrypointHandlers, CliNamespace
from sqlbuild.cli.commands.main.helpers.lineage.constants import COLUMN_LINEAGE_MODE_VALUES
from sqlbuild.cli.commands.main.helpers.playground.constants import PLAYGROUND_TEMPLATE_VALUES
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.parsers import (
    add_cursor_override_args,
    add_dbt_config_args,
    add_execution_args,
    add_execution_json_output_arg,
    add_scenario_snapshot_safety_args,
    add_select_args,
    add_vars_args,
    read_selector_files,
)
from sqlbuild.cli.commands.main.shared.types import CliCommand
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.planner.models import CursorOverrides
from sqlbuild.diagnostics.main.configure import configure_diagnostics
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.shared.constants import (
    SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED,
    SCENARIO_CLI_LOCAL_SNAPSHOT_FLAG_REQUIRED,
    SCENARIO_CLI_MISSING_SUBCOMMAND,
)
from sqlbuild.shared.helpers.colors import supports_color


def _build_parser(*, use_color: bool = False) -> argparse.ArgumentParser:
    """Build the root CLI parser."""

    parser_class: type[SqlbuildArgumentParser] = build_argument_parser_class(use_color=use_color)
    parser: argparse.ArgumentParser = parser_class(prog="sqb")
    parser.add_argument("--project-dir", default=None)
    parser.add_argument("--no-color", action="store_true", default=False)
    parser.add_argument("--debug", action="store_true", default=False)

    subparsers: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(
        dest="command",
        parser_class=parser_class,
    )
    compile_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.COMPILE)
    compile_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    compile_parser.add_argument("--defer-to", default=None)
    compile_parser.add_argument("--json", action="store_true", default=False)
    compile_parser.add_argument("--manifest", action="store_true", default=False)
    compile_parser.add_argument("--dag", nargs="?", const="", default=None)
    compile_parser.add_argument(
        "--lineage-mode",
        dest="compile_lineage_mode",
        choices=COMPILE_LINEAGE_MODE_VALUES,
        default=CompileLineageMode.FAST.value,
        help="Column lineage mode: fast (default), rich (slower), or none",
    )
    add_vars_args(compile_parser)
    add_dbt_config_args(compile_parser)

    dag_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.DAG)
    dag_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    dag_parser.add_argument("--json", action="store_true", default=False)
    add_vars_args(dag_parser)
    add_dbt_config_args(dag_parser)

    plan_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.PLAN)
    plan_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    plan_parser.add_argument("--defer-to", default=None)
    plan_parser.add_argument("--defer-sources-to", default=None)
    plan_parser.add_argument("--json", action="store_true", default=False)
    plan_parser.add_argument("--full-refresh", action="store_true", default=False)
    plan_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    plan_load_group: argparse._MutuallyExclusiveGroup = plan_parser.add_mutually_exclusive_group()
    plan_load_group.add_argument("--load", dest="load_sources", action="store_true", default=None)
    plan_load_group.add_argument("--no-load", dest="load_sources", action="store_false")
    add_cursor_override_args(plan_parser)
    add_select_args(plan_parser)
    add_vars_args(plan_parser)
    add_dbt_config_args(plan_parser)

    build_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.BUILD)
    build_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    build_parser.add_argument("--defer-to", default=None)
    build_parser.add_argument("--defer-sources-to", default=None)
    build_parser.add_argument("--json", action="store_true", default=False)
    add_execution_json_output_arg(build_parser)
    add_cursor_override_args(build_parser)
    build_load_group: argparse._MutuallyExclusiveGroup = build_parser.add_mutually_exclusive_group()
    build_load_group.add_argument("--load", dest="load_sources", action="store_true", default=None)
    build_load_group.add_argument("--no-load", dest="load_sources", action="store_false")
    build_load_group.add_argument("--reload", dest="reload", action="store_true", default=False)
    add_execution_args(build_parser)
    add_select_args(build_parser)
    add_vars_args(build_parser)
    add_dbt_config_args(build_parser)

    run_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.RUN)
    run_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    run_parser.add_argument("--defer-to", default=None)
    run_parser.add_argument("--defer-sources-to", default=None)
    run_parser.add_argument("--json", action="store_true", default=False)
    add_execution_json_output_arg(run_parser)
    add_cursor_override_args(run_parser)
    run_load_group: argparse._MutuallyExclusiveGroup = run_parser.add_mutually_exclusive_group()
    run_load_group.add_argument("--load", dest="load_sources", action="store_true", default=None)
    run_load_group.add_argument("--no-load", dest="load_sources", action="store_false")
    run_load_group.add_argument("--reload", dest="reload", action="store_true", default=False)
    add_execution_args(run_parser)
    add_select_args(run_parser)
    add_vars_args(run_parser)
    add_dbt_config_args(run_parser)

    test_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.TEST)
    test_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    test_parser.add_argument("--json", action="store_true", default=False)
    add_execution_json_output_arg(test_parser)
    add_select_args(test_parser)
    add_vars_args(test_parser)
    add_dbt_config_args(test_parser)

    audit_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.AUDIT)
    audit_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    audit_parser.add_argument("--defer-to", default=None)
    audit_parser.add_argument("--json", action="store_true", default=False)
    add_execution_json_output_arg(audit_parser)
    add_select_args(audit_parser)
    add_vars_args(audit_parser)
    add_dbt_config_args(audit_parser)

    load_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.LOAD)
    load_parser.add_argument("--reload", action="store_true", default=False)
    load_parser.add_argument("--json", action="store_true", default=False)
    load_parser.add_argument("--concurrency", type=int, default=None)
    add_execution_json_output_arg(load_parser)
    add_select_args(load_parser)
    add_cursor_override_args(load_parser)
    add_vars_args(load_parser)

    seed_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.SEED)
    seed_parser.add_argument("--json", action="store_true", default=False)
    seed_parser.add_argument("--concurrency", type=int, default=None)
    add_execution_json_output_arg(seed_parser)
    add_select_args(seed_parser)
    add_vars_args(seed_parser)

    clone_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.CLONE)
    clone_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    clone_parser.add_argument("--from", dest="from_environment", required=True)
    clone_parser.add_argument("--to", dest="to_environment", required=True)
    clone_parser.add_argument("--hard-copy", action="store_true", default=False)
    add_select_args(clone_parser)
    add_vars_args(clone_parser)
    add_dbt_config_args(clone_parser)

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
    add_vars_args(diff_parser)
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
    lineage_parser.add_argument(
        "--mode",
        dest="lineage_mode",
        choices=COLUMN_LINEAGE_MODE_VALUES,
        default=ColumnLineageMode.RICH.value,
        help="Column lineage mode: rich (default) or fast",
    )
    add_select_args(lineage_parser)
    add_vars_args(lineage_parser)
    subparsers.add_parser(CliCommand.CLEAN)
    janitor_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.JANITOR)
    janitor_parser.add_argument("--auto-approve", action="store_true", default=False)
    janitor_parser.add_argument("--retention-days", type=int, default=None)
    subparsers.add_parser(CliCommand.INIT)
    playground_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.PLAYGROUND)
    playground_parser.add_argument(
        "playground_path",
        nargs="?",
        default="sqlbuild-playground",
        metavar="path",
    )
    playground_parser.add_argument(
        "--template",
        dest="playground_template",
        choices=PLAYGROUND_TEMPLATE_VALUES,
        default="waffle_shop",
    )
    scenario_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.SCENARIO)
    scenario_subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
    scenario_subparsers = scenario_parser.add_subparsers(dest="scenario_command")
    scenario_test_parser: argparse.ArgumentParser = scenario_subparsers.add_parser("test")
    scenario_test_parser.add_argument("scenario_selector", nargs="*", metavar="scenario")
    scenario_test_parser.add_argument("--retain", dest="scenario_retain", action="store_true")
    scenario_test_parser.add_argument("--local", dest="scenario_local", action="store_true")
    scenario_test_parser.add_argument("--strict", dest="scenario_strict", action="store_true")
    scenario_test_parser.add_argument("--json", action="store_true", default=False)
    add_execution_json_output_arg(scenario_test_parser)
    add_select_args(scenario_test_parser)
    scenario_snapshot_group: argparse._MutuallyExclusiveGroup = (
        scenario_test_parser.add_mutually_exclusive_group()
    )
    scenario_snapshot_group.add_argument(
        "--sync-snapshots", dest="scenario_sync_snapshots", action="store_true"
    )
    scenario_snapshot_group.add_argument("--refresh", dest="scenario_refresh", action="store_true")
    add_scenario_snapshot_safety_args(scenario_test_parser)
    scenario_capture_parser: argparse.ArgumentParser = scenario_subparsers.add_parser("capture")
    scenario_capture_parser.add_argument("scenario_selector", nargs="*", metavar="scenario")
    scenario_capture_parser.add_argument("--retain", dest="scenario_retain", action="store_true")
    add_select_args(scenario_capture_parser)
    add_scenario_snapshot_safety_args(scenario_capture_parser)
    dbt_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.DBT)
    dbt_subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
    dbt_subparsers = dbt_parser.add_subparsers(dest="dbt_command")
    dbt_subparsers.add_parser("plan")
    dbt_subparsers.add_parser("run")
    dbt_subparsers.add_parser("build")
    dbt_subparsers.add_parser("test")
    dbt_subparsers.add_parser("debug")
    skills_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.SKILLS)
    skills_subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
    skills_subparsers = skills_parser.add_subparsers(dest="skills_command")
    skills_update_parser: argparse.ArgumentParser = skills_subparsers.add_parser("update")
    skills_update_parser.add_argument("--global", dest="skills_global", action="store_true")
    skills_update_parser.add_argument(
        "--target",
        dest="skills_target",
        action="append",
        choices=("opencode", "claude", "agents"),
        default=[],
    )
    skills_update_parser.add_argument("--force", dest="skills_force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entrypoint."""

    from sqlbuild.cli.commands.main.audit import run_audit
    from sqlbuild.cli.commands.main.build import run_build
    from sqlbuild.cli.commands.main.clone import run_clone
    from sqlbuild.cli.commands.main.compile import run_compile
    from sqlbuild.cli.commands.main.dag import run_dag
    from sqlbuild.cli.commands.main.dbt import run_dbt_command
    from sqlbuild.cli.commands.main.debug import run_debug
    from sqlbuild.cli.commands.main.diff import run_diff
    from sqlbuild.cli.commands.main.helpers.scenario.capture import run_scenario_capture
    from sqlbuild.cli.commands.main.janitor import run_janitor
    from sqlbuild.cli.commands.main.lineage import run_lineage
    from sqlbuild.cli.commands.main.load import run_load
    from sqlbuild.cli.commands.main.plan import run_plan
    from sqlbuild.cli.commands.main.playground import run_playground
    from sqlbuild.cli.commands.main.query import run_query
    from sqlbuild.cli.commands.main.run import run_run
    from sqlbuild.cli.commands.main.scenario import run_scenario
    from sqlbuild.cli.commands.main.seed import run_seed
    from sqlbuild.cli.commands.main.skills import run_skills_update
    from sqlbuild.cli.commands.main.test import run_test

    handlers: CliEntrypointHandlers = CliEntrypointHandlers(
        run_compile=run_compile,
        run_dag=run_dag,
        run_plan=run_plan,
        run_dbt_plan=lambda project_dir, args, no_color: run_dbt_command(
            command=DbtInteropCommand.PLAN,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_run=lambda project_dir, args, no_color: run_dbt_command(
            command=DbtInteropCommand.RUN,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_build=lambda project_dir, args, no_color: run_dbt_command(
            command=DbtInteropCommand.BUILD,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_test=lambda project_dir, args, no_color: run_dbt_command(
            command=DbtInteropCommand.TEST,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_debug=lambda project_dir, args, no_color: run_dbt_command(
            command=DbtInteropCommand.DEBUG,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_build=run_build,
        run_run=run_run,
        run_test=run_test,
        run_audit=run_audit,
        run_seed=run_seed,
        run_load=run_load,
        run_clone=run_clone,
        run_diff=run_diff,
        run_query=run_query,
        run_debug=run_debug,
        run_lineage=run_lineage,
        run_janitor=run_janitor,
        run_playground=run_playground,
        run_skills_update=run_skills_update,
        run_scenario=run_scenario,
        run_scenario_capture=run_scenario_capture,
    )
    return _main_with_dependencies(argv=argv, handlers=handlers)


def _main_with_dependencies(
    argv: Sequence[str] | None = None,
    *,
    handlers: CliEntrypointHandlers,
) -> int:
    """Run the CLI entrypoint with injected handlers for testing."""

    use_color: bool = cli_error_use_color(argv, supports_color=supports_color)
    parser: argparse.ArgumentParser = _build_parser(use_color=use_color)
    try:
        args: CliNamespace = CliNamespace()
        unknown_args: list[str]
        _, unknown_args = parser.parse_known_args(argv, namespace=args)
        if args.command == CliCommand.DBT and args.dbt_command in {
            "plan",
            "run",
            "build",
            "test",
            "debug",
        }:
            args.dbt_args = unknown_args
        elif unknown_args:
            parser.error(f"unrecognized arguments: {' '.join(unknown_args)}")
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
        select: tuple[str, ...] = (*tuple(args.select), *read_selector_files(args.select_file))
        if args.command == CliCommand.COMPILE:
            return handlers.run_compile(
                project_dir,
                args.no_sql_validation,
                args.defer_to,
                args.json,
                args.manifest,
                args.dag,
                args.no_color,
                CompileLineageMode(args.compile_lineage_mode),
                args.vars,
            )
        if args.command == CliCommand.DAG:
            return handlers.run_dag(
                project_dir,
                args.no_sql_validation,
                args.json,
                args.vars,
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
                args.defer_sources_to,
                cursor_overrides,
                args.json,
                args.full_refresh,
                args.load_sources,
                args.no_color,
                select,
                tuple(args.exclude),
                args.verbose,
                args.vars,
            )
        if args.command == CliCommand.DBT:
            if args.dbt_command == "plan":
                return handlers.run_dbt_plan(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "run":
                return handlers.run_dbt_run(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "build":
                return handlers.run_dbt_build(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "test":
                return handlers.run_dbt_test(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "debug":
                return handlers.run_dbt_debug(project_dir, tuple(args.dbt_args), args.no_color)
            raise CliUserError("dbt requires a subcommand such as 'plan'", code="C237")
        if args.command == CliCommand.BUILD:
            cursor_overrides = CursorOverrides(
                start_ts=None,
                end_ts=args.end_cursor_ts,
                start_int=args.start_cursor_int,
                end_int=args.end_cursor_int,
            )
            return handlers.run_build(
                project_dir,
                args.no_sql_validation,
                args.defer_to,
                args.defer_sources_to,
                cursor_overrides,
                args.no_color,
                args.fail_fast,
                args.full_refresh,
                args.load_sources,
                args.reload,
                args.allow_snapshot_full_refresh,
                args.allow_snapshot_schema_change,
                args.concurrency,
                select,
                tuple(args.exclude),
                args.verbose,
                args.debug,
                args.vars,
                args.json,
                args.json_output,
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
                args.defer_sources_to,
                cursor_overrides,
                args.no_color,
                args.fail_fast,
                args.full_refresh,
                args.load_sources,
                args.reload,
                args.allow_snapshot_full_refresh,
                args.allow_snapshot_schema_change,
                args.concurrency,
                select,
                tuple(args.exclude),
                args.verbose,
                args.debug,
                args.vars,
                args.json,
                args.json_output,
            )
        if args.command == CliCommand.TEST:
            return handlers.run_test(
                project_dir,
                args.no_sql_validation,
                args.no_color,
                select,
                tuple(args.exclude),
                args.vars,
                args.json,
                args.json_output,
            )
        if args.command == CliCommand.AUDIT:
            return handlers.run_audit(
                project_dir,
                args.no_sql_validation,
                args.defer_to,
                args.no_color,
                select,
                tuple(args.exclude),
                args.vars,
                args.json,
                args.json_output,
            )
        if args.command == CliCommand.LOAD:
            cursor_overrides = CursorOverrides(
                start_ts=args.start_cursor_ts,
                end_ts=args.end_cursor_ts,
                start_int=args.start_cursor_int,
                end_int=args.end_cursor_int,
            )
            return handlers.run_load(
                project_dir,
                args.no_color,
                select,
                tuple(args.exclude),
                args.reload,
                args.concurrency,
                cursor_overrides,
                args.vars,
                args.json,
                args.json_output,
            )
        if args.command == CliCommand.SEED:
            return handlers.run_seed(
                project_dir,
                args.no_color,
                select,
                tuple(args.exclude),
                args.concurrency,
                args.vars,
                args.json,
                args.json_output,
            )
        if args.command == CliCommand.LINEAGE:
            return handlers.run_lineage(
                project_dir,
                args.no_sql_validation,
                args.lineage_target,
                args.lineage_format,
                args.lineage_direction,
                args.lineage_depth,
                select,
                tuple(args.exclude),
                ColumnLineageMode(args.lineage_mode),
                args.vars,
            )
        if args.command == CliCommand.CLONE:
            if args.from_environment is None or args.to_environment is None:
                raise CliUserError("clone requires --from and --to", code="C406")
            return handlers.run_clone(
                project_dir,
                args.no_color,
                args.no_sql_validation,
                args.from_environment,
                args.to_environment,
                args.hard_copy,
                select,
                tuple(args.exclude),
                args.vars,
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
                select,
                tuple(args.exclude),
                args.verbose,
                args.vars,
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
        if args.command == CliCommand.PLAYGROUND:
            return handlers.run_playground(
                project_dir, args.playground_path, args.playground_template
            )
        if args.command == CliCommand.SKILLS:
            if args.skills_command == "update":
                return handlers.run_skills_update(
                    project_dir,
                    args.skills_global,
                    tuple(args.skills_target),
                    args.skills_force,
                )
            raise CliUserError("skills requires a subcommand such as 'update'", code="C807")
        if args.command == CliCommand.SCENARIO:
            scenario_select: tuple[str, ...] = (*tuple(args.scenario_selector), *select)
            if args.scenario_command == "test":
                if args.scenario_local and args.scenario_retain:
                    raise CliUserError(
                        "scenario test --local does not support --retain",
                        code=SCENARIO_CLI_LOCAL_RETAIN_UNSUPPORTED,
                        help=(
                            "Local scenario DuckDB files are always kept under "
                            "target/run/scenarios/."
                        ),
                    )
                if not args.scenario_local and (
                    args.scenario_sync_snapshots or args.scenario_refresh
                ):
                    raise CliUserError(
                        "scenario snapshot sync flags require --local",
                        code=SCENARIO_CLI_LOCAL_SNAPSHOT_FLAG_REQUIRED,
                        help=(
                            "Use sqb scenario test --local --sync-snapshots or "
                            "sqb scenario test --local --refresh."
                        ),
                    )
                return handlers.run_scenario(
                    project_dir,
                    False,
                    args.no_color,
                    scenario_select,
                    tuple(args.exclude),
                    args.scenario_retain,
                    args.scenario_local,
                    args.scenario_strict,
                    args.scenario_sync_snapshots,
                    args.scenario_refresh,
                    args.scenario_force,
                    args.scenario_max_snapshot_rows,
                    args.scenario_max_snapshot_total_rows,
                    args.scenario_max_snapshot_bytes,
                    args.scenario_max_snapshot_total_bytes,
                    args.json,
                    args.json_output,
                )
            if args.scenario_command == "capture":
                return handlers.run_scenario_capture(
                    project_dir,
                    False,
                    args.no_color,
                    scenario_select,
                    tuple(args.exclude),
                    args.scenario_retain,
                    args.scenario_force,
                    args.scenario_max_snapshot_rows,
                    args.scenario_max_snapshot_total_rows,
                    args.scenario_max_snapshot_bytes,
                    args.scenario_max_snapshot_total_bytes,
                )
            raise CliUserError(
                "scenario requires a subcommand such as 'test'",
                code=SCENARIO_CLI_MISSING_SUBCOMMAND,
            )
        return 0
    except CliUserError as error:
        logging.getLogger("sqlbuild.cli").exception("cli user error")
        print(
            format_expected_error(error, fallback_code="C000", use_color=use_color),
            file=sys.stderr,
        )
        return 1
    except (DiscoveryError, ValueError) as error:
        logging.getLogger("sqlbuild.cli").exception("command failed")
        print(
            format_expected_error(error, fallback_code="E001", use_color=use_color),
            file=sys.stderr,
        )
        return 1
