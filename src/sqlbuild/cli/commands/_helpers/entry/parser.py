"""Root CLI parser construction."""

from __future__ import annotations

import argparse

from sqlbuild.cli.commands._helpers.entry.errors import build_argument_parser_class
from sqlbuild.cli.commands._helpers.entry.parser_arguments import (
    add_cursor_override_args,
    add_dbt_config_args,
    add_execution_args,
    add_execution_json_output_arg,
    add_scenario_snapshot_safety_args,
    add_select_args,
    add_vars_args,
)
from sqlbuild.cli.commands.classes.sqlbuild_argument_parser import SqlbuildArgumentParser
from sqlbuild.cli.commands.constants import (
    COLUMN_LINEAGE_MODE_VALUES,
    COMPILE_LINEAGE_MODE_VALUES,
    PLAYGROUND_TEMPLATE_VALUES,
)
from sqlbuild.cli.commands.types import CliCommand, CompileLineageMode
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.virtual.state.types import StateCommand


def build_cli_parser(*, use_color: bool = False) -> argparse.ArgumentParser:
    """Build the root CLI parser."""

    parser_class: type[SqlbuildArgumentParser] = build_argument_parser_class(use_color=use_color)
    parser: argparse.ArgumentParser = parser_class(prog="sqb")
    parser.add_argument("--project-dir", "--sqb-project-dir", dest="project_dir", default=None)
    parser.add_argument("--no-color", action="store_true", default=False)
    parser.add_argument("--debug", action="store_true", default=False)

    subparsers: argparse._SubParsersAction[argparse.ArgumentParser] = parser.add_subparsers(
        dest="command",
        parser_class=parser_class,
    )
    _add_compile_and_dag_parsers(subparsers)
    _add_plan_and_build_parsers(subparsers)
    _add_quality_parsers(subparsers)
    _add_data_parsers(subparsers)
    _add_virtual_parsers(subparsers)
    _add_inspection_parsers(subparsers)
    _add_maintenance_parsers(subparsers)
    _add_workspace_parsers(subparsers)
    _add_dbt_parsers(subparsers)
    _add_skills_parsers(subparsers)
    _add_kata_parser(subparsers)
    return parser


def _add_compile_and_dag_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    compile_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.COMPILE)
    compile_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    compile_parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Bypass the compile analysis cache for this invocation",
    )
    compile_parser.add_argument("--defer-to", default=None)
    compile_parser.add_argument("--target", default=None)
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
    compile_parser.add_argument(
        "--profile-skip-discovery-sql-analysis",
        action="store_true",
        default=False,
        help="Diagnostic: skip SQL analysis-assisted discovery parsing",
    )
    compile_parser.add_argument(
        "--profile-skip-column-inference",
        action="store_true",
        default=False,
        help="Diagnostic: skip compile-time column inference",
    )
    compile_parser.add_argument(
        "--profile-skip-contracts",
        action="store_true",
        default=False,
        help="Diagnostic: skip offline contract validation",
    )
    compile_parser.add_argument(
        "--profile-skip-write",
        action="store_true",
        default=False,
        help="Diagnostic: skip writing target/compiled artifacts",
    )
    _ = add_vars_args(compile_parser)
    _ = add_dbt_config_args(parser=compile_parser)

    dag_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.DAG)
    dag_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    dag_parser.add_argument("--json", action="store_true", default=False)
    _ = add_vars_args(dag_parser)
    _ = add_dbt_config_args(parser=dag_parser)


def _add_plan_and_build_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    plan_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.PLAN)
    plan_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    plan_parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Bypass the compile analysis cache for this invocation",
    )
    plan_parser.add_argument("--defer-to", default=None)
    plan_parser.add_argument("--defer-sources-to", default=None)
    plan_parser.add_argument("--target", default=None)
    plan_parser.add_argument("--json", action="store_true", default=False)
    plan_parser.add_argument("--full-refresh", action="store_true", default=False)
    plan_parser.add_argument("--virtual-env", default=None)
    plan_parser.add_argument("--include-stale-upstreams", action="store_true", default=False)
    plan_parser.add_argument(
        "--changes-only",
        action="store_true",
        default=False,
        help="Only include resources that require execution.",
    )
    plan_parser.add_argument(
        "--no-python", dest="include_python", action="store_false", default=True
    )
    plan_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    plan_load_group: argparse._MutuallyExclusiveGroup = plan_parser.add_mutually_exclusive_group()
    plan_load_group.add_argument("--load", dest="load_sources", action="store_true", default=None)
    plan_load_group.add_argument("--no-load", dest="load_sources", action="store_false")
    _ = add_cursor_override_args(plan_parser)
    _ = add_select_args(plan_parser)
    _ = add_vars_args(plan_parser)
    _ = add_dbt_config_args(parser=plan_parser)

    build_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.BUILD)
    build_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    build_parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Bypass the compile analysis cache for this invocation",
    )
    build_parser.add_argument("--defer-to", default=None)
    build_parser.add_argument("--defer-clone-from", default=None)
    build_parser.add_argument("--defer-sources-to", default=None)
    build_parser.add_argument("--target", default=None)
    build_parser.add_argument("--json", action="store_true", default=False)
    build_parser.add_argument("--virtual-env", default=None)
    build_parser.add_argument("--include-stale-upstreams", action="store_true", default=False)
    build_parser.add_argument(
        "--changes-only",
        action="store_true",
        default=False,
        help="Only include resources that require execution.",
    )
    build_parser.add_argument(
        "--no-python", dest="include_python", action="store_false", default=True
    )
    build_parser.add_argument("--no-tests", dest="run_tests", action="store_false", default=True)
    build_parser.add_argument("--no-audits", dest="run_audits", action="store_false", default=True)
    build_parser.add_argument("--manifest", action="store_true", default=False)
    _ = add_execution_json_output_arg(build_parser)
    _ = add_cursor_override_args(build_parser)
    build_load_group: argparse._MutuallyExclusiveGroup = build_parser.add_mutually_exclusive_group()
    build_load_group.add_argument("--load", dest="load_sources", action="store_true", default=None)
    build_load_group.add_argument("--no-load", dest="load_sources", action="store_false")
    build_load_group.add_argument("--reload", dest="reload", action="store_true", default=False)
    _ = add_execution_args(build_parser)
    _ = add_select_args(build_parser)
    _ = add_vars_args(build_parser)
    _ = add_dbt_config_args(parser=build_parser)


def _add_quality_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    freshness_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.FRESHNESS)
    freshness_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    freshness_parser.add_argument("--json", action="store_true", default=False)
    freshness_parser.add_argument("--state", action="store_true", default=False)
    freshness_parser.add_argument("--target", default=None)
    freshness_parser.add_argument("--virtual-env", default=None)
    freshness_parser.add_argument("--fail-on-error", action="store_true", default=False)
    freshness_parser.add_argument("--fail-on-stale", action="store_true", default=False)
    _ = add_execution_json_output_arg(freshness_parser)
    _ = add_select_args(freshness_parser)
    _ = add_vars_args(freshness_parser)
    _ = add_dbt_config_args(parser=freshness_parser)

    test_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.TEST)
    test_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    test_parser.add_argument("--json", action="store_true", default=False)
    test_parser.add_argument("--target", default=None)
    _ = add_execution_json_output_arg(test_parser)
    _ = add_select_args(test_parser)
    _ = add_vars_args(test_parser)
    _ = add_dbt_config_args(parser=test_parser)

    check_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.CHECK)
    check_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    check_parser.add_argument("--json", action="store_true", default=False)
    check_parser.add_argument("--target", default=None)
    _ = add_execution_json_output_arg(check_parser)
    _ = add_select_args(check_parser)
    _ = add_vars_args(check_parser)
    _ = add_dbt_config_args(parser=check_parser)

    audit_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.AUDIT)
    audit_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    audit_parser.add_argument("--defer-to", default=None)
    audit_parser.add_argument("--target", default=None)
    audit_parser.add_argument("--json", action="store_true", default=False)
    _ = add_execution_json_output_arg(audit_parser)
    _ = add_select_args(audit_parser)
    _ = add_vars_args(audit_parser)
    _ = add_dbt_config_args(parser=audit_parser)

    lint_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.LINT)
    lint_parser.add_argument("--no-sqruff", dest="no_sqruff", action="store_true", default=False)

    format_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.FORMAT)
    format_parser.add_argument("--no-sqruff", dest="no_sqruff", action="store_true", default=False)


def _add_data_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    load_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.LOAD)
    load_parser.add_argument("--reload", action="store_true", default=False)
    load_parser.add_argument("--json", action="store_true", default=False)
    load_parser.add_argument("--target", default=None)
    load_parser.add_argument("--concurrency", type=int, default=None)
    _ = add_execution_json_output_arg(load_parser)
    _ = add_select_args(load_parser)
    _ = add_cursor_override_args(load_parser)
    _ = add_vars_args(load_parser)

    seed_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.SEED)
    seed_parser.add_argument("--json", action="store_true", default=False)
    seed_parser.add_argument("--target", default=None)
    seed_parser.add_argument("--concurrency", type=int, default=None)
    _ = add_execution_json_output_arg(seed_parser)
    _ = add_select_args(seed_parser)
    _ = add_vars_args(seed_parser)

    clone_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.CLONE)
    clone_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    clone_parser.add_argument("--from", dest="from_target", required=True)
    clone_parser.add_argument("--to", dest="to_target", default=None)
    clone_parser.add_argument("--hard-copy", action="store_true", default=False)
    clone_parser.add_argument("--virtual-env", default=None)
    clone_parser.add_argument("--skip-locked", action="store_true", default=False)
    clone_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    _ = add_select_args(clone_parser)
    _ = add_vars_args(clone_parser)
    _ = add_dbt_config_args(parser=clone_parser)

    diff_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.DIFF)
    diff_parser.add_argument("target_range", metavar="FROM:TO")
    diff_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    diff_parser.add_argument("--full", action="store_true", default=False)
    diff_parser.add_argument("--schema-only", action="store_true", default=False)
    diff_parser.add_argument("--bounded", default=None)
    diff_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    diff_parser.add_argument("--max-column-examples", type=int, default=None)
    diff_parser.add_argument("--max-row-only-examples", type=int, default=None)
    diff_parser.add_argument("--allow-partial-diff", action="store_true", default=False)
    _ = add_select_args(diff_parser)
    _ = add_vars_args(diff_parser)


def _add_virtual_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    reconcile_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.RECONCILE)
    reconcile_parser.add_argument("--virtual-env", dest="virtual_env", default=None)
    reconcile_parser.add_argument("--model", dest="reconcile_model", default=None)
    reconcile_parser.add_argument("--seed", dest="reconcile_seed", default=None)
    reconcile_subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
    reconcile_subparsers = reconcile_parser.add_subparsers(dest="reconcile_command")
    reconcile_repair_view_parser: argparse.ArgumentParser = reconcile_subparsers.add_parser(
        "repair-view"
    )
    reconcile_repair_view_parser.add_argument("--virtual-env", dest="virtual_env", default=None)
    reconcile_repair_view_parser.add_argument("--model", dest="reconcile_model", default=None)
    reconcile_repair_view_parser.add_argument("--seed", dest="reconcile_seed", default=None)
    reconcile_attach_parser: argparse.ArgumentParser = reconcile_subparsers.add_parser("attach")
    reconcile_attach_parser.add_argument("--virtual-env", dest="virtual_env", default=None)
    reconcile_attach_parser.add_argument("--model", dest="reconcile_model", required=True)
    reconcile_attach_parser.add_argument(
        "--physical-relation", dest="reconcile_physical_relation", required=True
    )
    reconcile_attach_parser.add_argument("--auto-approve", action="store_true", default=False)

    promote_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.PROMOTE)
    promote_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    promote_parser.add_argument("--from", dest="from_virtual_environment", required=True)
    promote_parser.add_argument("--to", dest="to_virtual_environment", required=True)
    promote_parser.add_argument("--allow-partial-promotion", action="store_true", default=False)
    promote_parser.add_argument("--include-stale-upstreams", action="store_true", default=False)
    promote_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    _ = add_select_args(promote_parser)
    _ = add_vars_args(promote_parser)

    rollback_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.ROLLBACK)
    rollback_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    rollback_parser.add_argument("--virtual-env", dest="virtual_env", default=None)
    rollback_parser.add_argument("--checkpoint-id", dest="rollback_checkpoint_id", default=None)
    rollback_parser.add_argument("--allow-partial-rollback", action="store_true", default=False)
    rollback_parser.add_argument("--include-stale-upstreams", action="store_true", default=False)
    rollback_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    _ = add_select_args(rollback_parser)
    _ = add_vars_args(rollback_parser)


def _add_inspection_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    scope_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.SCOPE)
    scope_parser.add_argument("scope_target", nargs="?", metavar="TARGET")
    scope_parser.add_argument("--at", dest="scope_at", default=None, metavar="PATH")
    scope_parser.add_argument("--as-path", dest="scope_as_path", default=None, metavar="PATH")
    browse_group: argparse._MutuallyExclusiveGroup = scope_parser.add_mutually_exclusive_group()
    browse_group.add_argument("--browse", dest="scope_browse", default=None, metavar="PATH")
    browse_group.add_argument("--list", dest="scope_list", default=None, metavar="PATH")
    scope_parser.add_argument("--defined-under", dest="scope_defined_under", default=None)
    scope_parser.add_argument(
        "--kind",
        dest="scope_kind",
        action="append",
        choices=("macro", "enum", "constant"),
        default=[],
    )
    scope_parser.add_argument("--match", dest="scope_match", default=None, metavar="GLOB")
    scope_parser.add_argument("--used-only", dest="scope_used_only", action="store_true")
    scope_parser.add_argument("--include-nearby", dest="scope_include_nearby", action="store_true")
    scope_parser.add_argument("--nearby-depth", dest="scope_nearby_depth", type=int, default=1)
    scope_parser.add_argument(
        "--dependency-depth", dest="scope_dependency_depth", type=int, default=0
    )
    scope_parser.add_argument("--explain", dest="scope_explain", default=None)
    scope_parser.add_argument(
        "--globals", dest="scope_globals", choices=("summary", "used", "all"), default="summary"
    )
    scope_parser.add_argument("--page-size", dest="scope_page_size", type=int, default=100)
    scope_parser.add_argument("--after", dest="scope_after", default=None, metavar="CURSOR")
    scope_parser.add_argument(
        "--paths", dest="scope_paths", choices=("relative", "compact", "none"), default="relative"
    )
    scope_parser.add_argument("--json", action="store_true", default=False)
    scope_parser.add_argument("--no-cache", action="store_true", default=False)

    debug_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.DEBUG)
    debug_parser.add_argument("--json", action="store_true", default=False)
    debug_parser.add_argument("--target", default=None)
    debug_parser.add_argument("--no-connection", action="store_true", default=False)

    cost_parser: argparse.ArgumentParser = subparsers.add_parser(
        CliCommand.COST,
        help="show persisted Snowflake busy-compute estimates",
    )
    cost_parser.add_argument(
        "cost_selector",
        nargs="?",
        default="latest",
        metavar="latest|history|run_id",
    )
    cost_parser.add_argument(
        "--limit", dest="cost_limit", type=int, default=None, help="limit returned rows"
    )
    cost_parser.add_argument(
        "--no-limit",
        dest="cost_no_limit",
        action="store_true",
        default=False,
        help="return all matching rows",
    )
    cost_parser.add_argument(
        "--sort", dest="cost_sort", default=None, help="metric used to sort results"
    )
    cost_parser.add_argument(
        "--order",
        dest="cost_order",
        choices=("asc", "desc"),
        default=None,
        help="sort direction",
    )
    cost_parser.add_argument(
        "--since",
        dest="cost_since",
        default=None,
        help="inclusive ISO date/datetime or relative duration such as 7d",
    )
    cost_parser.add_argument(
        "--until",
        dest="cost_until",
        default=None,
        help="inclusive ISO date or timezone-aware datetime",
    )
    cost_parser.add_argument(
        "--json", action="store_true", default=False, help="write stable JSON to stdout"
    )
    _ = add_execution_json_output_arg(cost_parser)

    query_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.QUERY)
    query_parser.add_argument("query_sql", nargs="?", metavar="sql")
    query_parser.add_argument("--file", dest="query_file", default=None)
    query_parser.add_argument("--target", default=None)
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
    _ = add_select_args(lineage_parser)
    _ = add_vars_args(lineage_parser)


def _add_maintenance_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    subparsers.add_parser(CliCommand.CLEAN)
    janitor_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.JANITOR)
    janitor_parser.add_argument("--auto-approve", action="store_true", default=False)
    janitor_parser.add_argument("--retention-days", type=int, default=None)
    janitor_parser.add_argument("--direct-state-history-versions", type=int, default=None)

    state_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.STATE)
    state_subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
    state_subparsers = state_parser.add_subparsers(dest="state_command")
    state_subparsers.add_parser(StateCommand.INIT.value)
    state_subparsers.add_parser(StateCommand.MIGRATE.value)
    state_adopt_parser: argparse.ArgumentParser = state_subparsers.add_parser(
        StateCommand.ADOPT.value
    )
    state_adopt_parser.add_argument("--allow-copy", action="store_true", default=False)
    state_detach_parser: argparse.ArgumentParser = state_subparsers.add_parser(
        StateCommand.DETACH.value
    )
    state_detach_parser.add_argument("--allow-copy", action="store_true", default=False)
    state_rollback_parser: argparse.ArgumentParser = state_subparsers.add_parser(
        StateCommand.ROLLBACK.value
    )
    state_rollback_parser.add_argument("--backup-id", dest="state_backup_id", default=None)
    state_reset_parser: argparse.ArgumentParser = state_subparsers.add_parser(
        StateCommand.RESET.value
    )
    state_reset_parser.add_argument("--auto-approve", action="store_true", default=False)
    state_checkpoints_parser: argparse.ArgumentParser = state_subparsers.add_parser("checkpoints")
    state_checkpoints_subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
    state_checkpoints_subparsers = state_checkpoints_parser.add_subparsers(
        dest="state_checkpoint_command"
    )
    state_checkpoints_list_parser: argparse.ArgumentParser = (
        state_checkpoints_subparsers.add_parser("list")
    )
    state_checkpoints_list_parser.add_argument("--virtual-env", dest="virtual_env", default=None)
    state_checkpoints_show_parser: argparse.ArgumentParser = (
        state_checkpoints_subparsers.add_parser("show")
    )
    state_checkpoints_show_parser.add_argument("state_checkpoint_id", metavar="checkpoint_id")
    state_checkpoints_show_parser.add_argument("--virtual-env", dest="virtual_env", default=None)
    state_checkpoints_diff_parser: argparse.ArgumentParser = (
        state_checkpoints_subparsers.add_parser("diff")
    )
    state_checkpoints_diff_parser.add_argument("state_checkpoint_id", metavar="checkpoint_id")
    state_checkpoints_diff_parser.add_argument("--virtual-env", dest="virtual_env", default=None)


def _add_workspace_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
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
    _ = add_execution_json_output_arg(scenario_test_parser)
    _ = add_select_args(scenario_test_parser)
    scenario_snapshot_group: argparse._MutuallyExclusiveGroup = (
        scenario_test_parser.add_mutually_exclusive_group()
    )
    scenario_snapshot_group.add_argument(
        "--sync-snapshots", dest="scenario_sync_snapshots", action="store_true"
    )
    scenario_snapshot_group.add_argument("--refresh", dest="scenario_refresh", action="store_true")
    _ = add_scenario_snapshot_safety_args(scenario_test_parser)
    scenario_capture_parser: argparse.ArgumentParser = scenario_subparsers.add_parser("capture")
    scenario_capture_parser.add_argument("scenario_selector", nargs="*", metavar="scenario")
    scenario_capture_parser.add_argument("--retain", dest="scenario_retain", action="store_true")
    _ = add_select_args(scenario_capture_parser)
    _ = add_scenario_snapshot_safety_args(scenario_capture_parser)


def _add_dbt_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    dbt_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.DBT)
    dbt_subparsers: argparse._SubParsersAction[argparse.ArgumentParser]
    dbt_subparsers = dbt_parser.add_subparsers(dest="dbt_command")
    dbt_subparsers.add_parser("plan", add_help=False)
    dbt_subparsers.add_parser("run", add_help=False)
    dbt_subparsers.add_parser("build", add_help=False)
    dbt_subparsers.add_parser("debug")
    dbt_init_parser: argparse.ArgumentParser = dbt_subparsers.add_parser("init")
    dbt_init_parser.add_argument("--project-dir", dest="dbt_project_dir", default=None)
    dbt_init_parser.add_argument("--profiles-dir", dest="dbt_profiles_dir", default=None)
    dbt_init_parser.add_argument("--profile", dest="dbt_profile", default=None)
    dbt_init_parser.add_argument("--target", dest="dbt_target", default=None)
    dbt_init_parser.add_argument("--sqb-output-dir", dest="sqb_output_dir", default=None)
    dbt_init_parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=False)
    dbt_init_parser.add_argument(
        "--overwrite", dest="overwrite", action="store_true", default=False
    )
    dbt_init_parser.add_argument(
        "--skip-dbt-debug", dest="skip_dbt_debug", action="store_true", default=False
    )


def _add_skills_parsers(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    skills_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.SKILLS)
    skills_parser.add_argument("--global", dest="skills_global", action="store_true")
    skills_parser.add_argument(
        "--target",
        dest="skills_target",
        action="append",
        choices=("opencode", "claude", "agents"),
        default=[],
    )
    skills_parser.add_argument("--force", dest="skills_force", action="store_true")


def _add_kata_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    kata_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.KATA)
    kata_parser.add_argument("--json", action="store_true", default=False)
    add_select_args(kata_parser)
    kata_subparsers: argparse._SubParsersAction[argparse.ArgumentParser] = (
        kata_parser.add_subparsers(dest="kata_command")
    )
    rule_parser: argparse.ArgumentParser = kata_subparsers.add_parser("rule")
    rule_parser.add_argument("kata_rule_code")
    skills_parser: argparse.ArgumentParser = kata_subparsers.add_parser("skills")
    skills_parser.add_argument("--check", dest="kata_skills_check", action="store_true")
