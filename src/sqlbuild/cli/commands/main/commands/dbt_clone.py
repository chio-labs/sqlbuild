"""CLI dbt clone command entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from sqlbuild.cli.commands.helpers.clone.output import (
    is_clone_success,
    render_clone_header,
    render_clone_item_line,
    render_clone_output,
)
from sqlbuild.cli.commands.shared.helpers.progress.planning import PlanningProgressReporter
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.integrations.dbt.models import DbtCloneRun
from sqlbuild.integrations.dbt.pipeline.main.clone import run_dbt_clone_from_project
from sqlbuild.shared.helpers.output.colors import supports_color


def run_dbt_clone_command(
    *, project_dir: Path | None, args: tuple[str, ...], no_color: bool
) -> int:
    """Execute `sqb dbt clone`."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stderr
    item_stream: TextIO = sys.stdout
    progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    streamed_state: dict[str, bool] = {"started": False}

    def _on_clone_start(origin_target_name: str, destination_target_name: str, total: int) -> None:
        progress.finish()
        item_stream.write(
            render_clone_header(
                origin_target_name=origin_target_name,
                destination_target_name=destination_target_name,
                total=total,
                use_color=use_color,
            )
            + "\n"
        )
        item_stream.flush()
        streamed_state["started"] = True

    def _on_clone_item(index: int, total: int, item: CloneItemResult) -> None:
        if not streamed_state["started"]:
            progress.finish()
            streamed_state["started"] = True
        item_stream.write(
            render_clone_item_line(index=index, total=total, item=item, use_color=use_color) + "\n"
        )
        item_stream.flush()

    try:
        clone_run: DbtCloneRun = run_dbt_clone_from_project(
            project_dir=effective_project_dir,
            args=args,
            on_progress=progress.on_progress,
            on_clone_start=_on_clone_start,
            on_item=_on_clone_item,
        )
    finally:
        progress.finish(blank_line_after=False)
    render_clone_output(
        result=clone_run.result,
        use_color=use_color,
    )
    return 0 if is_clone_success(clone_run.result) else 1
