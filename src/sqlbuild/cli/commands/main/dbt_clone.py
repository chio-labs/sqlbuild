"""CLI dbt clone command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands.main.helpers.clone.output import is_clone_success, render_clone_output
from sqlbuild.cli.commands.main.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.integrations.dbt.models import DbtCloneRun
from sqlbuild.integrations.dbt.pipeline.main.clone import run_dbt_clone_from_project
from sqlbuild.shared.helpers.colors import supports_color


def run_dbt_clone_command(
    *, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    """Execute `sqb dbt clone`."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr
    progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    try:
        clone_run: DbtCloneRun = run_dbt_clone_from_project(
            project_dir=effective_project_dir,
            args=args,
            on_progress=progress.on_progress,
        )
    finally:
        progress.finish(blank_line_after=True)
    render_clone_output(
        result=clone_run.result,
        origin_target_name=clone_run.origin_label,
        destination_target_name=clone_run.destination_label,
        use_color=use_color,
    )
    return 0 if is_clone_success(clone_run.result) else 1
