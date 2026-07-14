"""Streaming callbacks for dbt clone CLI output."""

from __future__ import annotations

from typing import TextIO, cast

from sqlbuild.cli.commands.constants import (
    DBT_CLONE_INDEX_ARGUMENT,
    DBT_CLONE_ORIGIN_TARGET_NAME_ARGUMENT,
)
from sqlbuild.cli.commands.helpers.clone.output import render_clone_header, render_clone_item_line
from sqlbuild.cli.progress.classes.planning_progress_reporter import PlanningProgressReporter
from sqlbuild.executor.clone.models import CloneItemResult


class DbtCloneStreamCallbacks:
    """Render dbt clone start and item events to the CLI stream."""

    def __init__(
        self,
        *,
        progress: PlanningProgressReporter,
        item_stream: TextIO,
        use_color: bool,
    ) -> None:
        self._progress: PlanningProgressReporter = progress
        self._item_stream: TextIO = item_stream
        self._use_color: bool = use_color
        self._started: bool = False

    def on_start(self, *args: object, **kwargs: object) -> None:
        origin_target_name: str = cast(
            str,
            kwargs[DBT_CLONE_ORIGIN_TARGET_NAME_ARGUMENT]
            if DBT_CLONE_ORIGIN_TARGET_NAME_ARGUMENT in kwargs
            else args[0],
        )
        self._progress.finish()
        self._item_stream.write(
            render_clone_header(
                origin_target_name=origin_target_name,
                destination_target_name=cast(str, kwargs["destination_target_name"]),
                total=cast(int, kwargs["total"]),
                use_color=self._use_color,
            )
            + "\n"
        )
        self._item_stream.flush()
        self._started = True

    def on_item(self, *args: object, **kwargs: object) -> None:
        if not self._started:
            self._progress.finish()
            self._started = True
        index: int = cast(
            int,
            kwargs[DBT_CLONE_INDEX_ARGUMENT] if DBT_CLONE_INDEX_ARGUMENT in kwargs else args[0],
        )
        self._item_stream.write(
            render_clone_item_line(
                index=index,
                total=cast(int, kwargs["total"]),
                item=cast(CloneItemResult, kwargs["item"]),
                use_color=self._use_color,
            )
            + "\n"
        )
        self._item_stream.flush()
