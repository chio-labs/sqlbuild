"""CLI entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from sqlbuild.cli.commands.helpers.entry.dispatch import dispatch_cli_command
from sqlbuild.cli.commands.helpers.entry.errors import (
    cli_error_use_color,
    format_expected_error,
)
from sqlbuild.cli.commands.helpers.entry.models import (
    CliEntrypointHandlers,
    ParsedCliInvocation,
)
from sqlbuild.cli.commands.helpers.entry.parser import build_cli_parser
from sqlbuild.cli.commands.helpers.entry.parsing import parse_cli_invocation
from sqlbuild.cli.commands.shared.exceptions import CliUserError
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.shared.helpers.output.colors import supports_color
from sqlbuild.virtual.state.exceptions import StateBackendError


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entrypoint."""

    from sqlbuild.cli.commands.helpers.scenario.capture import run_scenario_capture
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
        run_dbt_init=run_dbt_init_command,
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
