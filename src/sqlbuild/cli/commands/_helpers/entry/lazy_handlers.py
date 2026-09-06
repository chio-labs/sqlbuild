"""Lazy command implementation loading for the CLI entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from types import ModuleType
from typing import Any, cast

from sqlbuild.cli.commands.models import CliEntrypointHandlers
from sqlbuild.integrations.dbt.types import DbtInteropCommand


def build_lazy_cli_handlers() -> CliEntrypointHandlers:
    """Build command handlers that import only the selected implementation."""

    lazy: dict[str, Callable[..., int]] = {
        "scenario_capture": _lazy_handler(
            module_name="sqlbuild.cli.commands._helpers.scenario_capture.capture",
            function_name="run_scenario_capture",
        ),
        "dbt": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.dbt._dbt",
            function_name="run_dbt_command",
        ),
        "dbt_init": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.dbt._dbt_init",
            function_name="run_dbt_init_command",
        ),
        "audit": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.execution._audit",
            function_name="run_audit",
        ),
        "build": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.execution._build",
            function_name="run_build",
        ),
        "check": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.execution._check",
            function_name="run_check",
        ),
        "freshness": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.execution._freshness",
            function_name="run_freshness",
        ),
        "load": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.execution._load",
            function_name="run_load",
        ),
        "scenario": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.execution._scenario",
            function_name="run_scenario",
        ),
        "seed": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.execution._seed",
            function_name="run_seed",
        ),
        "test": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.execution._test",
            function_name="run_test",
        ),
        "clone": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.inspection._clone",
            function_name="run_clone",
        ),
        "cost": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.inspection._cost",
            function_name="run_cost",
        ),
        "debug": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.inspection._debug",
            function_name="run_debug",
        ),
        "diff": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.inspection._diff",
            function_name="run_diff",
        ),
        "lineage": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.inspection._lineage",
            function_name="run_lineage",
        ),
        "query": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.inspection._query",
            function_name="run_query",
        ),
        "scope": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.inspection._scope",
            function_name="run_scope",
        ),
        "compile": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.project._compile",
            function_name="run_compile",
        ),
        "dag": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.project._dag",
            function_name="run_dag",
        ),
        "format": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.project._format",
            function_name="run_format_command",
        ),
        "fix": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.project._fix",
            function_name="run_fix_command",
        ),
        "kata": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.project._kata",
            function_name="run_kata_command",
        ),
        "lint": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.project._lint",
            function_name="run_lint_command",
        ),
        "plan": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.project._plan",
            function_name="run_plan",
        ),
        "janitor": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.state._janitor",
            function_name="run_janitor",
        ),
        "promote": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.state._promote",
            function_name="run_promote",
        ),
        "reconcile": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.state._reconcile",
            function_name="run_reconcile",
        ),
        "rollback": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.state._rollback",
            function_name="run_rollback",
        ),
        "state": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.state._state",
            function_name="run_state",
        ),
        "init": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.workspace._init",
            function_name="run_init",
        ),
        "playground": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.workspace._playground",
            function_name="run_playground",
        ),
        "skills": _lazy_handler(
            module_name="sqlbuild.cli.commands.main.workspace._skills",
            function_name="run_skills_update",
        ),
    }
    return CliEntrypointHandlers(
        run_compile=lazy["compile"],
        run_cost=lazy["cost"],
        run_dag=lambda project_dir, no_sql_validation, json_output, cli_vars: lazy["dag"](
            project_dir=project_dir,
            no_sql_validation=no_sql_validation,
            json_output=json_output,
            cli_vars=cli_vars,
        ),
        run_plan=lazy["plan"],
        run_dbt_plan=lambda project_dir, args, no_color: lazy["dbt"](
            command=DbtInteropCommand.PLAN,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_run=lambda project_dir, args, no_color: lazy["dbt"](
            command=DbtInteropCommand.RUN,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_build=lambda project_dir, args, no_color: lazy["dbt"](
            command=DbtInteropCommand.BUILD,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_debug=lambda project_dir, args, no_color: lazy["dbt"](
            command=DbtInteropCommand.DEBUG,
            project_dir=project_dir,
            args=args,
            no_color=no_color,
        ),
        run_dbt_init=lazy["dbt_init"],
        run_build=lazy["build"],
        run_freshness=lazy["freshness"],
        run_test=lazy["test"],
        run_check=lazy["check"],
        run_audit=lazy["audit"],
        run_seed=lazy["seed"],
        run_load=lazy["load"],
        run_clone=lazy["clone"],
        run_diff=lazy["diff"],
        run_reconcile=lambda project_dir, no_color, virtual_environment, reconcile_command, model_name, seed_name, physical_relation_name, auto_approve, cli_vars: (  # noqa: E501
            lazy["reconcile"](
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
        run_promote=lazy["promote"],
        run_rollback=lazy["rollback"],
        run_query=lambda project_dir, sql, query_file, selected_target, output_format, limit: lazy[
            "query"
        ](
            project_dir=project_dir,
            sql=sql,
            query_file=query_file,
            selected_target=selected_target,
            output_format=output_format,
            limit=limit,
        ),
        run_debug=lambda project_dir, no_color, no_connection, selected_target, json_output: lazy[
            "debug"
        ](
            project_dir=project_dir,
            no_color=no_color,
            no_connection=no_connection,
            selected_target=selected_target,
            json_output=json_output,
        ),
        run_lineage=lambda project_dir, no_sql_validation, target, output_format, direction, depth, select, exclude, lineage_mode, cli_vars: (  # noqa: E501
            lazy["lineage"](
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
        run_janitor=lazy["janitor"],
        run_state=lambda project_dir, state_command, backup_id, auto_approve, no_color, checkpoint_command, checkpoint_id, virtual_environment, allow_copy: (  # noqa: E501
            lazy["state"](
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
        run_init=lazy["init"],
        run_playground=lazy["playground"],
        run_skills_update=lambda project_dir, global_install, targets, force: lazy["skills"](
            project_dir=project_dir,
            global_install=global_install,
            targets=targets,
            force=force,
        ),
        run_lint=lambda project_dir, select, exclude, json_output, no_color: lazy["lint"](
            project_dir=project_dir,
            select=select,
            exclude=exclude,
            json_output=json_output,
            no_color=no_color,
        ),
        run_format=lambda project_dir, select, exclude, check, diff, json_output, no_color: lazy[
            "format"
        ](
            project_dir=project_dir,
            select=select,
            exclude=exclude,
            check=check,
            diff=diff,
            json_output=json_output,
            no_color=no_color,
        ),
        run_fix=lambda project_dir, select, exclude, check, diff, json_output, no_color: lazy[
            "fix"
        ](
            project_dir=project_dir,
            select=select,
            exclude=exclude,
            check=check,
            diff=diff,
            json_output=json_output,
            no_color=no_color,
        ),
        run_scenario=lazy["scenario"],
        run_scenario_capture=lazy["scenario_capture"],
        run_kata=lazy["kata"],
        run_scope=lazy["scope"],
    )


def _lazy_handler(*, module_name: str, function_name: str) -> Callable[..., int]:
    """Load one command implementation only when its handler is invoked."""

    def run(*args: Any, **kwargs: Any) -> int:
        module: ModuleType = import_module(module_name)
        handler: Callable[..., int] = cast(
            Callable[..., int],
            getattr(module, function_name),
        )
        return handler(*args, **kwargs)

    return run
