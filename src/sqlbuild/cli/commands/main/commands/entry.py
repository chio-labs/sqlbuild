"""CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlbuild.cli.commands.main.helpers.compile.constants import COMPILE_LINEAGE_MODE_VALUES
from sqlbuild.cli.commands.main.helpers.compile.types import CompileLineageMode
from sqlbuild.cli.commands.main.helpers.diff.validation import parse_diff_name_range
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
from sqlbuild.cli.commands.main.shared.helpers.config.parsers import (
    add_cursor_override_args,
    add_dbt_config_args,
    add_execution_args,
    add_execution_json_output_arg,
    add_scenario_snapshot_safety_args,
    add_select_args,
    add_vars_args,
    read_selector_files,
    resolve_env_default_concurrency,
)
from sqlbuild.cli.commands.main.shared.types import CliCommand
from sqlbuild.compiler.discovery.constants import PROJECT_CONFIG_FILENAME
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
from sqlbuild.shared.helpers.output.colors import supports_color
from sqlbuild.virtual.state.exceptions import StateBackendError
from sqlbuild.virtual.state.types import StateCommand


def _build_parser(*, use_color: bool = False) -> argparse.ArgumentParser:
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
    compile_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.COMPILE)
    compile_parser.add_argument("--no-sql-validation", action="store_true", default=False)
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
    plan_parser.add_argument("--target", default=None)
    plan_parser.add_argument("--json", action="store_true", default=False)
    plan_parser.add_argument("--full-refresh", action="store_true", default=False)
    plan_parser.add_argument("--virtual-env", default=None)
    plan_parser.add_argument("--include-stale-upstreams", action="store_true", default=False)
    plan_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Include selected resources even when unchanged.",
    )
    plan_parser.add_argument(
        "--no-python", dest="include_python", action="store_false", default=True
    )
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
    build_parser.add_argument("--defer-clone-from", default=None)
    build_parser.add_argument("--defer-sources-to", default=None)
    build_parser.add_argument("--target", default=None)
    build_parser.add_argument("--json", action="store_true", default=False)
    build_parser.add_argument("--virtual-env", default=None)
    build_parser.add_argument("--include-stale-upstreams", action="store_true", default=False)
    build_parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Include selected resources even when unchanged.",
    )
    build_parser.add_argument(
        "--no-python", dest="include_python", action="store_false", default=True
    )
    build_parser.add_argument("--no-tests", dest="run_tests", action="store_false", default=True)
    build_parser.add_argument("--no-audits", dest="run_audits", action="store_false", default=True)
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

    freshness_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.FRESHNESS)
    freshness_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    freshness_parser.add_argument("--json", action="store_true", default=False)
    freshness_parser.add_argument("--state", action="store_true", default=False)
    freshness_parser.add_argument("--target", default=None)
    freshness_parser.add_argument("--virtual-env", default=None)
    freshness_parser.add_argument("--fail-on-error", action="store_true", default=False)
    freshness_parser.add_argument("--fail-on-stale", action="store_true", default=False)
    add_execution_json_output_arg(freshness_parser)
    add_select_args(freshness_parser)
    add_vars_args(freshness_parser)
    add_dbt_config_args(freshness_parser)

    test_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.TEST)
    test_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    test_parser.add_argument("--json", action="store_true", default=False)
    test_parser.add_argument("--target", default=None)
    add_execution_json_output_arg(test_parser)
    add_select_args(test_parser)
    add_vars_args(test_parser)
    add_dbt_config_args(test_parser)

    check_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.CHECK)
    check_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    check_parser.add_argument("--json", action="store_true", default=False)
    check_parser.add_argument("--target", default=None)
    add_execution_json_output_arg(check_parser)
    add_select_args(check_parser)
    add_vars_args(check_parser)
    add_dbt_config_args(check_parser)

    audit_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.AUDIT)
    audit_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    audit_parser.add_argument("--defer-to", default=None)
    audit_parser.add_argument("--target", default=None)
    audit_parser.add_argument("--json", action="store_true", default=False)
    add_execution_json_output_arg(audit_parser)
    add_select_args(audit_parser)
    add_vars_args(audit_parser)
    add_dbt_config_args(audit_parser)

    load_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.LOAD)
    load_parser.add_argument("--reload", action="store_true", default=False)
    load_parser.add_argument("--json", action="store_true", default=False)
    load_parser.add_argument("--target", default=None)
    load_parser.add_argument("--concurrency", type=int, default=None)
    add_execution_json_output_arg(load_parser)
    add_select_args(load_parser)
    add_cursor_override_args(load_parser)
    add_vars_args(load_parser)

    seed_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.SEED)
    seed_parser.add_argument("--json", action="store_true", default=False)
    seed_parser.add_argument("--target", default=None)
    seed_parser.add_argument("--concurrency", type=int, default=None)
    add_execution_json_output_arg(seed_parser)
    add_select_args(seed_parser)
    add_vars_args(seed_parser)

    clone_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.CLONE)
    clone_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    clone_parser.add_argument("--from", dest="from_target", required=True)
    clone_parser.add_argument("--to", dest="to_target", required=True)
    clone_parser.add_argument("--hard-copy", action="store_true", default=False)
    clone_parser.add_argument("--virtual-env", default=None)
    clone_parser.add_argument("--skip-locked", action="store_true", default=False)
    clone_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    add_select_args(clone_parser)
    add_vars_args(clone_parser)
    add_dbt_config_args(clone_parser)

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
    add_select_args(diff_parser)
    add_vars_args(diff_parser)
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
    add_select_args(promote_parser)
    add_vars_args(promote_parser)
    rollback_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.ROLLBACK)
    rollback_parser.add_argument("--no-sql-validation", action="store_true", default=False)
    rollback_parser.add_argument("--virtual-env", dest="virtual_env", default=None)
    rollback_parser.add_argument("--checkpoint-id", dest="rollback_checkpoint_id", default=None)
    rollback_parser.add_argument("--allow-partial-rollback", action="store_true", default=False)
    rollback_parser.add_argument("--include-stale-upstreams", action="store_true", default=False)
    rollback_parser.add_argument("--verbose", "-v", action="store_true", default=False)
    add_select_args(rollback_parser)
    add_vars_args(rollback_parser)
    debug_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.DEBUG)
    debug_parser.add_argument("--json", action="store_true", default=False)
    debug_parser.add_argument("--target", default=None)
    debug_parser.add_argument("--no-connection", action="store_true", default=False)
    query_parser: argparse.ArgumentParser = subparsers.add_parser(CliCommand.QUERY)
    query_parser.add_argument("query_sql", nargs="?", metavar="sql")
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
    add_select_args(lineage_parser)
    add_vars_args(lineage_parser)
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
    dbt_subparsers.add_parser("plan", add_help=False)
    dbt_subparsers.add_parser("run", add_help=False)
    dbt_subparsers.add_parser("build", add_help=False)
    dbt_subparsers.add_parser("test", add_help=False)
    dbt_subparsers.add_parser("scenario")
    dbt_subparsers.add_parser("debug")
    dbt_subparsers.add_parser("lineage")
    dbt_subparsers.add_parser("diff")
    dbt_subparsers.add_parser("clone")
    dbt_init_parser: argparse.ArgumentParser = dbt_subparsers.add_parser("init")
    dbt_init_parser.add_argument("--project-dir", dest="dbt_project_dir", default=None)
    dbt_init_parser.add_argument("--profiles-dir", dest="dbt_profiles_dir", default=None)
    dbt_init_parser.add_argument("--profile", dest="dbt_profile", default=None)
    dbt_init_parser.add_argument("--target", dest="dbt_target", default=None)
    dbt_init_parser.add_argument("--prod-git-ref", dest="dbt_prod_git_ref", default=None)
    dbt_init_parser.add_argument("--sqb-output-dir", dest="sqb_output_dir", default=None)
    dbt_init_parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=False)
    dbt_init_parser.add_argument(
        "--overwrite", dest="overwrite", action="store_true", default=False
    )
    dbt_init_parser.add_argument(
        "--skip-dbt-debug", dest="skip_dbt_debug", action="store_true", default=False
    )
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

    from sqlbuild.cli.commands.main.commands.audit import run_audit
    from sqlbuild.cli.commands.main.commands.build import run_build
    from sqlbuild.cli.commands.main.commands.check import run_check
    from sqlbuild.cli.commands.main.commands.clone import run_clone
    from sqlbuild.cli.commands.main.commands.compile import run_compile
    from sqlbuild.cli.commands.main.commands.dag import run_dag
    from sqlbuild.cli.commands.main.commands.dbt import run_dbt_command
    from sqlbuild.cli.commands.main.commands.dbt_init import run_dbt_init_command
    from sqlbuild.cli.commands.main.commands.debug import run_debug
    from sqlbuild.cli.commands.main.commands.diff import run_diff
    from sqlbuild.cli.commands.main.commands.freshness import run_freshness
    from sqlbuild.cli.commands.main.commands.init import run_init
    from sqlbuild.cli.commands.main.commands.janitor import run_janitor
    from sqlbuild.cli.commands.main.commands.lineage import run_lineage
    from sqlbuild.cli.commands.main.commands.load import run_load
    from sqlbuild.cli.commands.main.commands.plan import run_plan
    from sqlbuild.cli.commands.main.commands.playground import run_playground
    from sqlbuild.cli.commands.main.commands.promote import run_promote
    from sqlbuild.cli.commands.main.commands.query import run_query
    from sqlbuild.cli.commands.main.commands.reconcile import run_reconcile
    from sqlbuild.cli.commands.main.commands.rollback import run_rollback
    from sqlbuild.cli.commands.main.commands.scenario import run_scenario
    from sqlbuild.cli.commands.main.commands.seed import run_seed
    from sqlbuild.cli.commands.main.commands.skills import run_skills_update
    from sqlbuild.cli.commands.main.commands.state import run_state
    from sqlbuild.cli.commands.main.commands.test import run_test
    from sqlbuild.cli.commands.main.helpers.scenario.capture import run_scenario_capture

    def run_dbt_init_positional(
        cwd: Path,
        dbt_project_dir: str | None,
        profiles_dir: str | None,
        profile_name: str | None,
        target_name: str | None,
        sqb_output_dir: str | None,
        dry_run: bool,
        overwrite: bool,
        skip_dbt_debug: bool,
        production_git_ref: str | None,
    ) -> int:
        return run_dbt_init_command(
            cwd=cwd,
            dbt_project_dir=dbt_project_dir,
            profiles_dir=profiles_dir,
            profile_name=profile_name,
            target_name=target_name,
            sqb_output_dir=sqb_output_dir,
            dry_run=dry_run,
            overwrite=overwrite,
            skip_dbt_debug=skip_dbt_debug,
            production_git_ref=production_git_ref,
        )

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
        run_dbt_scenario=lambda project_dir, args, no_color: run_dbt_command(
            command=DbtInteropCommand.SCENARIO,
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
        run_dbt_lineage=lambda project_dir, args, no_color: run_dbt_command(
            command=DbtInteropCommand.LINEAGE,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_diff=lambda project_dir, args, no_color: run_dbt_command(
            command=DbtInteropCommand.DIFF,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_clone=lambda project_dir, args, no_color: run_dbt_command(
            command=DbtInteropCommand.CLONE,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_init=run_dbt_init_positional,
        run_build=run_build,
        run_freshness=run_freshness,
        run_test=run_test,
        run_check=run_check,
        run_audit=run_audit,
        run_seed=run_seed,
        run_load=run_load,
        run_clone=run_clone,
        run_diff=run_diff,
        run_reconcile=run_reconcile,
        run_promote=run_promote,
        run_rollback=run_rollback,
        run_query=run_query,
        run_debug=run_debug,
        run_lineage=run_lineage,
        run_janitor=run_janitor,
        run_state=run_state,
        run_init=run_init,
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
            "scenario",
            "debug",
            "lineage",
            "diff",
            "clone",
        }:
            dbt_passthrough_args: list[str] = []
            dbt_arg: str
            for dbt_arg in unknown_args:
                if dbt_arg == "--no-color":
                    args.no_color = True
                    continue
                if dbt_arg == "--debug":
                    args.debug = True
                    continue
                dbt_passthrough_args.append(dbt_arg)
            args.dbt_args = dbt_passthrough_args
        elif unknown_args:
            parser.error(f"unrecognized arguments: {' '.join(unknown_args)}")
        if args.command in {CliCommand.BUILD, CliCommand.LOAD, CliCommand.SEED}:
            try:
                args.concurrency = resolve_env_default_concurrency(args.concurrency)
            except argparse.ArgumentTypeError as error:
                parser.error(str(error))
    except SystemExit as error:
        if isinstance(error.code, int):
            return error.code
        return 1

    try:
        project_dir: Path | None = None if args.project_dir is None else Path(args.project_dir)
        effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
        if args.command is not None and not (
            args.command == CliCommand.DBT
            and args.dbt_command != "init"
            and not (effective_project_dir / PROJECT_CONFIG_FILENAME).exists()
        ):
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
                args.target,
                args.json,
                args.manifest,
                args.dag,
                args.no_color,
                CompileLineageMode(args.compile_lineage_mode),
                args.vars,
                args.profile_skip_discovery_sql_analysis,
                args.profile_skip_column_inference,
                args.profile_skip_contracts,
                args.profile_skip_write,
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
                args.target,
                cursor_overrides,
                args.json,
                args.full_refresh,
                args.virtual_env,
                args.load_sources,
                args.include_python,
                args.no_color,
                select,
                tuple(args.exclude),
                args.verbose,
                args.vars,
                args.include_stale_upstreams,
                args.force,
            )
        if args.command == CliCommand.DBT:
            if args.dbt_command == "init":
                return handlers.run_dbt_init(
                    effective_project_dir,
                    args.dbt_project_dir,
                    args.dbt_profiles_dir,
                    args.dbt_profile,
                    args.dbt_target,
                    args.sqb_output_dir,
                    args.dry_run,
                    args.overwrite,
                    args.skip_dbt_debug,
                    args.dbt_prod_git_ref,
                )
            if args.dbt_command == "plan":
                return handlers.run_dbt_plan(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "run":
                return handlers.run_dbt_run(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "build":
                return handlers.run_dbt_build(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "test":
                return handlers.run_dbt_test(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "scenario":
                return handlers.run_dbt_scenario(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "debug":
                return handlers.run_dbt_debug(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "lineage":
                return handlers.run_dbt_lineage(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "diff":
                return handlers.run_dbt_diff(project_dir, tuple(args.dbt_args), args.no_color)
            if args.dbt_command == "clone":
                return handlers.run_dbt_clone(project_dir, tuple(args.dbt_args), args.no_color)
            raise CliUserError("dbt requires a subcommand such as 'plan'", code="C237")
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
                args.defer_clone_from,
                args.defer_sources_to,
                args.target,
                cursor_overrides,
                args.no_color,
                args.fail_fast,
                args.full_refresh,
                args.virtual_env,
                args.load_sources,
                args.reload,
                args.include_python,
                args.allow_snapshot_full_refresh,
                args.allow_snapshot_schema_change,
                args.concurrency,
                select,
                tuple(args.exclude),
                args.verbose,
                args.debug,
                args.vars,
                args.include_stale_upstreams,
                args.force,
                args.run_tests,
                args.run_audits,
                args.json,
                args.json_output,
            )
        if args.command == CliCommand.FRESHNESS:
            return handlers.run_freshness(
                project_dir,
                args.no_sql_validation,
                args.no_color,
                args.target,
                select,
                tuple(args.exclude),
                args.vars,
                args.json,
                args.json_output,
                args.fail_on_error,
                args.state,
                args.fail_on_stale,
                args.virtual_env,
            )
        if args.command == CliCommand.TEST:
            return handlers.run_test(
                project_dir,
                args.no_sql_validation,
                args.no_color,
                args.target,
                select,
                tuple(args.exclude),
                args.vars,
                args.json,
                args.json_output,
            )
        if args.command == CliCommand.CHECK:
            return handlers.run_check(
                project_dir,
                args.no_sql_validation,
                args.no_color,
                args.target,
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
                args.target,
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
                args.target,
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
                args.target,
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
            if args.from_target is None or args.to_target is None:
                raise CliUserError("clone requires --from and --to", code="C406")
            return handlers.run_clone(
                project_dir,
                args.no_color,
                args.no_sql_validation,
                args.from_target,
                args.to_target,
                args.hard_copy,
                args.virtual_env,
                args.skip_locked,
                select,
                tuple(args.exclude),
                args.verbose,
                args.vars,
            )
        if args.command == CliCommand.DIFF:
            from_name: str
            to_name: str
            from_name, to_name = parse_diff_name_range(args.target_range)
            return handlers.run_diff(
                project_dir,
                args.no_color,
                args.no_sql_validation,
                from_name,
                to_name,
                args.full,
                args.schema_only,
                args.bounded,
                args.max_column_examples,
                args.max_row_only_examples,
                select,
                tuple(args.exclude),
                args.verbose,
                args.vars,
                args.allow_partial_diff,
            )
        if args.command == CliCommand.RECONCILE:
            return handlers.run_reconcile(
                project_dir,
                args.no_color,
                args.virtual_env,
                args.reconcile_command,
                getattr(args, "reconcile_model", None),
                getattr(args, "reconcile_seed", None),
                getattr(args, "reconcile_physical_relation", None),
                getattr(args, "auto_approve", False),
                args.vars,
            )
        if args.command == CliCommand.PROMOTE:
            if args.from_virtual_environment is None or args.to_virtual_environment is None:
                raise CliUserError("promote requires --from and --to", code="C244")
            return handlers.run_promote(
                project_dir,
                args.no_color,
                args.no_sql_validation,
                args.from_virtual_environment,
                args.to_virtual_environment,
                select,
                tuple(args.exclude),
                args.allow_partial_promotion,
                args.include_stale_upstreams,
                args.verbose,
                args.vars,
            )
        if args.command == CliCommand.ROLLBACK:
            return handlers.run_rollback(
                project_dir,
                args.no_color,
                args.no_sql_validation,
                args.virtual_env,
                args.verbose,
                args.rollback_checkpoint_id,
                select,
                tuple(args.exclude),
                args.allow_partial_rollback,
                args.include_stale_upstreams,
                args.vars,
            )
        if args.command == CliCommand.QUERY:
            query_limit: int | None = None if args.query_no_limit else args.query_limit
            return handlers.run_query(
                project_dir,
                args.query_sql,
                args.target,
                args.query_format,
                query_limit,
            )
        if args.command == CliCommand.DEBUG:
            return handlers.run_debug(
                project_dir,
                args.no_color,
                args.no_connection,
                args.target,
                args.json,
            )
        if args.command == CliCommand.JANITOR:
            return handlers.run_janitor(
                project_dir,
                args.no_color,
                args.auto_approve,
                args.retention_days,
                args.direct_state_history_versions,
            )
        if args.command == CliCommand.STATE:
            if args.state_command is None:
                raise CliUserError("state requires a subcommand such as 'init'", code="C901")
            return handlers.run_state(
                project_dir,
                args.state_command,
                args.state_backup_id,
                args.auto_approve,
                args.no_color,
                args.state_checkpoint_command,
                args.state_checkpoint_id,
                args.virtual_env,
                getattr(args, "allow_copy", False),
            )
        if args.command == CliCommand.INIT:
            return handlers.run_init(project_dir)
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
    except SystemExit as error:
        if isinstance(error.code, int):
            return error.code
        return 1
    except CliUserError as error:
        logging.getLogger("sqlbuild.cli").exception("cli user error")
        print(
            format_expected_error(error, fallback_code="C000", use_color=use_color),
            file=sys.stderr,
        )
        return 1
    except (DiscoveryError, StateBackendError, ValueError) as error:
        logging.getLogger("sqlbuild.cli").exception("command failed")
        print(
            format_expected_error(error, fallback_code="E001", use_color=use_color),
            file=sys.stderr,
        )
        return 1
