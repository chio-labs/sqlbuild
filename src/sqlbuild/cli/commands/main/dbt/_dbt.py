"""CLI dbt interop command entry points."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands._helpers.dbt.auto_init import (
    ensure_sqlbuild_project_for_dbt_command,
)
from sqlbuild.cli.commands.constants import (
    DBT_CLI_OUTPUT_OPTIONS,
    DBT_JSON_OUTPUT_OPTION,
    DBT_VERBOSE_OPTIONS,
)
from sqlbuild.cli.commands.main.dbt._dbt_clone import run_dbt_clone_command
from sqlbuild.cli.commands.main.dbt._dbt_debug import run_dbt_debug_command
from sqlbuild.cli.commands.main.dbt._dbt_diff import run_dbt_diff_command
from sqlbuild.cli.commands.main.dbt._dbt_scenario import run_dbt_scenario_command
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.integrations.dbt.main.cli.validate_execution_args import validate_dbt_execution_args
from sqlbuild.integrations.dbt.main.pipeline.execute import execute_dbt_interop_from_project
from sqlbuild.integrations.dbt.main.pipeline.plan import plan_dbt_interop_from_project
from sqlbuild.integrations.dbt.main.pipeline.render_plan import (
    render_dbt_interop_plan,
)
from sqlbuild.integrations.dbt.models import DbtInteropExecutionRequest, DbtInteropPlan
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.presentation.models import DisplayOptions


def run_dbt_command(
    *, command: DbtInteropCommand, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    """Execute one `sqb dbt` interop command."""

    validate_dbt_execution_args(command=command, args=args)
    effective_project_dir: Path
    forwarded_args: tuple[str, ...]
    effective_project_dir, forwarded_args = ensure_sqlbuild_project_for_dbt_command(
        project_dir=project_dir,
        args=args,
        no_color=no_color,
    )
    if command == DbtInteropCommand.PLAN:
        return _run_dbt_plan(
            project_dir=effective_project_dir, args=forwarded_args, no_color=no_color
        )
    if command == DbtInteropCommand.DEBUG:
        return run_dbt_debug_command(
            project_dir=effective_project_dir, args=forwarded_args, no_color=no_color
        )
    if command == DbtInteropCommand.DIFF:
        return run_dbt_diff_command(
            project_dir=effective_project_dir, args=forwarded_args, no_color=no_color
        )
    if command == DbtInteropCommand.CLONE:
        return run_dbt_clone_command(
            project_dir=effective_project_dir, args=forwarded_args, no_color=no_color
        )
    if command == DbtInteropCommand.SCENARIO:
        return run_dbt_scenario_command(
            project_dir=effective_project_dir, args=forwarded_args, no_color=no_color
        )
    return _run_dbt_execution_command(
        command=command,
        project_dir=effective_project_dir,
        args=forwarded_args,
        no_color=no_color,
    )


def _run_dbt_plan(
    *,
    project_dir: Path | None,
    args: tuple[str, ...],
    no_color: bool = False,
) -> int:
    """Execute `sqb dbt plan`."""

    json_output: bool = DBT_JSON_OUTPUT_OPTION in args
    verbose: bool = any(option in args for option in DBT_VERBOSE_OPTIONS)
    routed_args: tuple[str, ...] = tuple(arg for arg in args if arg not in DBT_CLI_OUTPUT_OPTIONS)
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and not json_output and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    if not json_output:
        progress_stream.write("\n")
        progress_stream.flush()
    plan: DbtInteropPlan = plan_dbt_interop_from_project(
        project_dir=effective_project_dir,
        args=routed_args,
        on_progress=planning_progress.on_progress,
        progress_stream=progress_stream,
        use_color=use_color,
    )
    display_options: DisplayOptions = DisplayOptions(
        max_entries_per_section=None if verbose else 10
    )
    print(
        render_dbt_interop_plan(
            plan=plan,
            json_output=json_output,
            use_color=use_color,
            display_options=display_options,
        )
    )
    return 0


def _run_dbt_execution_command(
    *, command: DbtInteropCommand, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    verbose: bool = any(option in args for option in DBT_VERBOSE_OPTIONS)
    json_output: bool = DBT_JSON_OUTPUT_OPTION in args
    routed_args: tuple[str, ...] = tuple(arg for arg in args if arg not in DBT_CLI_OUTPUT_OPTIONS)
    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and not json_output and supports_color()
    progress_stream: TextIO = sys.stderr if json_output else sys.stdout
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write("\n")
    progress_stream.flush()
    return execute_dbt_interop_from_project(
        DbtInteropExecutionRequest(
            command=command,
            project_dir=effective_project_dir,
            args=routed_args,
            on_progress=planning_progress.on_progress,
            progress_stream=progress_stream,
            dbt_stdout_stream=sys.stdout,
            use_color=use_color,
            verbose=verbose,
            json_output=json_output,
        )
    )
