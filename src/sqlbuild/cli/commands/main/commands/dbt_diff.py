"""CLI dbt diff command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands.helpers.diff.output import has_diff_failures, render_diff_output
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.integrations.dbt.models import DbtDiffRun
from sqlbuild.integrations.dbt.pipeline.main.diff import run_dbt_diff_from_project
from sqlbuild.presentation.main.supports_color import supports_color


def run_dbt_diff_command(*, project_dir: Path | None, args: tuple[str, ...], no_color: bool) -> int:
    """Execute `sqb dbt diff`."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr
    progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    diff_run: DbtDiffRun = run_dbt_diff_from_project(
        project_dir=effective_project_dir,
        args=args,
        on_progress=progress.on_progress,
    )
    print(
        render_diff_output(
            result=diff_run.result,
            from_label=diff_run.from_label,
            to_label=diff_run.to_label,
            mode_label=diff_run.mode_label,
            use_color=use_color,
            verbose=diff_run.verbose,
            max_column_examples=diff_run.max_column_examples,
            max_row_only_examples=diff_run.max_row_only_examples,
        )
    )
    return 1 if has_diff_failures(diff_run.result) else 0
