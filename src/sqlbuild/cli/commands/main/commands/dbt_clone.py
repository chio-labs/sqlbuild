"""CLI dbt clone command entry point."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO, cast

from sqlbuild.cli.commands.helpers.clone.output import (
    is_clone_success,
    render_clone_header,
    render_clone_item_line,
    render_clone_output,
)
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.integrations.dbt.models import DbtCloneRun
from sqlbuild.integrations.dbt.pipeline.main.clone import run_dbt_clone_from_project
from sqlbuild.shared.helpers.output.colors import supports_color


@dataclass
class _CloneStreamCallbacks:
    progress: PlanningProgressReporter
    item_stream: TextIO
    use_color: bool
    started: bool = False

    def on_start(self, *args: object, **kwargs: object) -> None:
        self.started = _on_clone_start(
            origin_target_name=cast(
                str, kwargs["origin_target_name"] if "origin_target_name" in kwargs else args[0]
            ),
            destination_target_name=cast(str, kwargs["destination_target_name"]),
            total=cast(int, kwargs["total"]),
            progress=self.progress,
            item_stream=self.item_stream,
            use_color=self.use_color,
        )

    def on_item(self, *args: object, **kwargs: object) -> None:
        self.started = _on_clone_item(
            index=cast(int, kwargs["index"] if "index" in kwargs else args[0]),
            total=cast(int, kwargs["total"]),
            item=cast(CloneItemResult, kwargs["item"]),
            progress=self.progress,
            item_stream=self.item_stream,
            started=self.started,
            use_color=self.use_color,
        )


def _on_clone_start(
    *,
    origin_target_name: str,
    destination_target_name: str,
    total: int,
    progress: PlanningProgressReporter,
    item_stream: TextIO,
    use_color: bool,
) -> bool:
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
    return True


def _on_clone_item(
    *,
    index: int,
    total: int,
    item: CloneItemResult,
    progress: PlanningProgressReporter,
    item_stream: TextIO,
    started: bool,
    use_color: bool,
) -> bool:
    if not started:
        progress.finish()
        started = True
    item_stream.write(
        render_clone_item_line(index=index, total=total, item=item, use_color=use_color) + "\n"
    )
    item_stream.flush()
    return started


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
    callbacks: _CloneStreamCallbacks = _CloneStreamCallbacks(
        progress=progress, item_stream=item_stream, use_color=use_color
    )

    try:
        clone_run: DbtCloneRun = run_dbt_clone_from_project(
            project_dir=effective_project_dir,
            args=args,
            on_progress=progress.on_progress,
            on_clone_start=callbacks.on_start,
            on_item=callbacks.on_item,
        )
    finally:
        progress.finish(blank_line_after=False)
    _ = render_clone_output(
        result=clone_run.result,
        use_color=use_color,
    )
    return 0 if is_clone_success(clone_run.result) else 1
