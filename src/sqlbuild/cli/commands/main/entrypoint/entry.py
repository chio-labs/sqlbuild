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
from sqlbuild.cli.commands._helpers.entry.parser import build_cli_parser
from sqlbuild.cli.commands._helpers.entry.parsing import parse_cli_invocation
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.cli.commands.models import (
    CliEntrypointHandlers,
    ParsedCliInvocation,
)
from sqlbuild.compiler.discovery.exceptions import DiscoveryError
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.virtual.state.exceptions import StateBackendError


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI entrypoint."""

    from sqlbuild.cli.commands._helpers.scenario_capture.capture import run_scenario_capture
    from sqlbuild.cli.commands.main.dbt._dbt import run_dbt_command
    from sqlbuild.cli.commands.main.dbt._dbt_init import run_dbt_init_command
    from sqlbuild.cli.commands.main.execution._audit import run_audit
    from sqlbuild.cli.commands.main.execution._build import run_build
    from sqlbuild.cli.commands.main.execution._check import run_check
    from sqlbuild.cli.commands.main.execution._freshness import run_freshness
    from sqlbuild.cli.commands.main.execution._load import run_load
    from sqlbuild.cli.commands.main.execution._scenario import run_scenario
    from sqlbuild.cli.commands.main.execution._seed import run_seed
    from sqlbuild.cli.commands.main.execution._test import run_test
    from sqlbuild.cli.commands.main.inspection._clone import run_clone
    from sqlbuild.cli.commands.main.inspection._debug import run_debug
    from sqlbuild.cli.commands.main.inspection._diff import run_diff
    from sqlbuild.cli.commands.main.inspection._lineage import run_lineage
    from sqlbuild.cli.commands.main.inspection._query import run_query
    from sqlbuild.cli.commands.main.project._compile import run_compile
    from sqlbuild.cli.commands.main.project._dag import run_dag
    from sqlbuild.cli.commands.main.project._plan import run_plan
    from sqlbuild.cli.commands.main.state._janitor import run_janitor
    from sqlbuild.cli.commands.main.state._promote import run_promote
    from sqlbuild.cli.commands.main.state._reconcile import run_reconcile
    from sqlbuild.cli.commands.main.state._rollback import run_rollback
    from sqlbuild.cli.commands.main.state._state import run_state
    from sqlbuild.cli.commands.main.workspace._init import run_init
    from sqlbuild.cli.commands.main.workspace._playground import run_playground
    from sqlbuild.cli.commands.main.workspace._skills import run_skills_update

    handlers: CliEntrypointHandlers = CliEntrypointHandlers(
        run_compile=run_compile,
        run_dag=lambda project_dir, no_sql_validation, json_output, cli_vars: run_dag(
            project_dir=project_dir,
            no_sql_validation=no_sql_validation,
            json_output=json_output,
            cli_vars=cli_vars,
        ),
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
        run_reconcile=lambda project_dir, no_color, virtual_environment, reconcile_command, model_name, seed_name, physical_relation_name, auto_approve, cli_vars: (  # noqa: E501
            run_reconcile(
                project_dir=project_dir,
                no_color=no_color,
                virtual_environment=virtual_environment,
                reconcile_command=reconcile_command,
                model_name=model_name,
                seed_name=seed_name,
                physical_relation_name=physical_relation_name,
                auto_approve=auto_approve,
                cli_vars=cli_vars,
            )
        ),
        run_promote=run_promote,
        run_rollback=run_rollback,
        run_query=lambda project_dir, sql, query_file, selected_target, output_format, limit: (
            run_query(
                project_dir=project_dir,
                sql=sql,
                query_file=query_file,
                selected_target=selected_target,
                output_format=output_format,
                limit=limit,
            )
        ),
        run_debug=lambda project_dir, no_color, no_connection, selected_target, json_output: (
            run_debug(
                project_dir=project_dir,
                no_color=no_color,
                no_connection=no_connection,
                selected_target=selected_target,
                json_output=json_output,
            )
        ),
        run_lineage=lambda project_dir, no_sql_validation, target, output_format, direction, depth, select, exclude, lineage_mode, cli_vars: (  # noqa: E501
            run_lineage(
                project_dir=project_dir,
                no_sql_validation=no_sql_validation,
                target=target,
                output_format=output_format,
                direction=direction,
                depth=depth,
                select=select,
                exclude=exclude,
                lineage_mode=lineage_mode,
                cli_vars=cli_vars,
            )
        ),
        run_janitor=run_janitor,
        run_state=lambda project_dir, state_command, backup_id, auto_approve, no_color, checkpoint_command, checkpoint_id, virtual_environment, allow_copy: (  # noqa: E501
            run_state(
                project_dir=project_dir,
                state_command=state_command,
                backup_id=backup_id,
                auto_approve=auto_approve,
                no_color=no_color,
                checkpoint_command=checkpoint_command,
                checkpoint_id=checkpoint_id,
                virtual_environment=virtual_environment,
                allow_copy=allow_copy,
            )
        ),
        run_init=run_init,
        run_playground=run_playground,
        run_skills_update=lambda project_dir, global_install, targets, force: run_skills_update(
            project_dir=project_dir,
            global_install=global_install,
            targets=targets,
            force=force,
        ),
        run_scenario=run_scenario,
        run_scenario_capture=run_scenario_capture,
    )
    return _main_with_dependencies(argv=argv, handlers=handlers)


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
    except CliUserError as error:
        logging.getLogger("sqlbuild.cli").exception("cli user error")
        print(
            format_expected_error(error=error, fallback_code="C000", use_color=use_color),
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
