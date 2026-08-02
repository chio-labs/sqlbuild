"""Clone command execution phases."""

from __future__ import annotations

import time
from typing import TextIO

from sqlbuild.cli.commands._helpers.clone.output import render_clone_item_line
from sqlbuild.cli.commands.models import (
    CloneCommandRequest,
    CloneConnectionContext,
    CloneExecutionPreparation,
    CloneInvocation,
    CloneRunOutcome,
)
from sqlbuild.executor.clone.main.execute import execute_clone
from sqlbuild.executor.clone.main.fingerprinting import copy_clone_fingerprints
from sqlbuild.executor.clone.models import (
    CloneExecutionResult,
    CloneItemResult,
    CloneSourceEntries,
)
from sqlbuild.executor.clone.types import CloneItemCallback


def execute_clone_plan(
    *,
    request: CloneCommandRequest,
    invocation: CloneInvocation,
    connection_context: CloneConnectionContext,
    preparation: CloneExecutionPreparation,
) -> CloneRunOutcome:
    """Execute the standard clone plan and copy fingerprints."""

    clone_start: float = time.monotonic()
    on_item: CloneItemCallback = _build_on_clone_item(
        stream=invocation.progress_stream,
        use_color=invocation.use_color,
    )
    result: CloneExecutionResult = execute_clone(
        source_entries=CloneSourceEntries(
            origin=preparation.pipeline_result.origin_source_entries,
            destination=preparation.pipeline_result.destination_source_entries,
        ),
        origin_model_entries=preparation.pipeline_result.origin_model_entries,
        destination_model_entries=preparation.pipeline_result.destination_model_entries,
        origin_seed_entries=preparation.pipeline_result.origin_seed_entries,
        destination_seed_entries=preparation.pipeline_result.destination_seed_entries,
        adapter=invocation.adapter,
        origin_connection=connection_context.origin_connection,
        destination_connection=connection_context.destination_connection,
        hard_copy=request.hard_copy,
        on_item=on_item,
    )
    copy_clone_fingerprints(
        result=result,
        origin_model_entries=preparation.pipeline_result.origin_model_entries,
        destination_model_entries=preparation.pipeline_result.destination_model_entries,
        origin_seed_entries=preparation.pipeline_result.origin_seed_entries,
        destination_seed_entries=preparation.pipeline_result.destination_seed_entries,
        adapter=invocation.adapter,
        origin_connection=connection_context.origin_connection,
        destination_connection=connection_context.destination_connection,
        run_id=preparation.pipeline_result.destination_project.run_id,
        query_change_tracking=preparation.pipeline_result.destination_project.settings.query_change_tracking,
    )
    return CloneRunOutcome(result=result, elapsed=time.monotonic() - clone_start)


def _build_on_clone_item(*, stream: TextIO, use_color: bool) -> CloneItemCallback:
    def _on_clone_item(*, index: int, total: int, item: CloneItemResult) -> None:
        stream.write(
            render_clone_item_line(index=index, total=total, item=item, use_color=use_color) + "\n"
        )
        stream.flush()

    return _on_clone_item
