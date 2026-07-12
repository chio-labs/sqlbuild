"""CLI dbt mixed-lineage command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.integrations.dbt.main.lineage import build_dbt_lineage_output
from sqlbuild.shared.helpers.output.colors import supports_color


def run_dbt_lineage_command(
    *, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    """Execute `sqb dbt lineage`."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr
    progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    print(
        build_dbt_lineage_output(
            project_dir=effective_project_dir,
            args=args,
            use_color=use_color,
            on_progress=progress.on_progress,
        )
    )
    return 0
