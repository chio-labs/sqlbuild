"""CLI dbt interop command entry points."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.integrations.dbt.models import DbtInteropPlan
from sqlbuild.integrations.dbt.pipeline.main.execute import execute_dbt_interop_from_project
from sqlbuild.integrations.dbt.pipeline.main.plan import plan_dbt_interop_from_project
from sqlbuild.integrations.dbt.pipeline.main.render_plan import (
    render_dbt_interop_plan,
)
from sqlbuild.integrations.dbt.types import DbtInteropCommand
from sqlbuild.shared.helpers.colors import supports_color
from sqlbuild.shared.helpers.display import DisplayOptions


def run_dbt_plan(
    project_dir: Path | None,
    args: tuple[str, ...],
    no_color: bool = False,
) -> int:
    """Execute `sqb dbt plan`."""

    json_output: bool = "--json" in args
    verbose: bool = "--verbose" in args or "-v" in args
    routed_args: tuple[str, ...] = tuple(
        arg for arg in args if arg not in {"--json", "--verbose", "-v"}
    )
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
        max_entries_per_section=None if verbose else 50
    )
    print(
        render_dbt_interop_plan(
            plan,
            json_output=json_output,
            use_color=use_color,
            display_options=display_options,
        )
    )
    return 0


def run_dbt_run(project_dir: Path | None, args: tuple[str, ...], no_color: bool = False) -> int:
    """Execute `sqb dbt run`."""

    return _run_dbt_execution_command(
        command=DbtInteropCommand.RUN,
        project_dir=project_dir,
        args=args,
        no_color=no_color,
    )


def run_dbt_build(project_dir: Path | None, args: tuple[str, ...], no_color: bool = False) -> int:
    """Execute `sqb dbt build`."""

    return _run_dbt_execution_command(
        command=DbtInteropCommand.BUILD,
        project_dir=project_dir,
        args=args,
        no_color=no_color,
    )


def _run_dbt_execution_command(
    *, command: DbtInteropCommand, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    verbose: bool = "--verbose" in args or "-v" in args
    json_output: bool = "--json" in args
    routed_args: tuple[str, ...] = tuple(
        arg for arg in args if arg not in {"--json", "--verbose", "-v"}
    )
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
