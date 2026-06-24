"""CLI dbt identity-diff command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands.main.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.integrations.dbt.main.identity_diff import build_dbt_identity_diff_output
from sqlbuild.shared.helpers.colors import supports_color


def run_dbt_identity_diff_command(
    *, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    """Execute `sqb dbt identity-diff`."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and "--json" not in args and supports_color()
    progress_stream: TextIO = sys.stderr
    progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    print(
        build_dbt_identity_diff_output(
            project_dir=effective_project_dir,
            args=args,
            use_color=use_color,
            on_progress=progress.on_progress,
        )
    )
    return 0
