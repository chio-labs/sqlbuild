"""Shared view recreation operation over an already-resolved destination and SQL."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus


def recreate_view_by_names(
    *,
    name: str,
    origin_relation: str,
    destination_relation: str,
    view_sql: str,
    origin_exists: bool,
    adapter: BaseAdapter,
    connection: Any,
) -> CloneItemResult:
    """Recreate the destination view from SQL, returning a timed item result."""

    if not origin_exists:
        return CloneItemResult(
            name=name,
            action=CloneAction.WARNING_MISSING_SOURCE,
            status=CloneStatus.WARNING,
            message="missing in origin environment",
            origin_relation=origin_relation,
            destination_relation=destination_relation,
        )
    recorder: StatementRecorder = StatementRecorder()
    start: float = time.monotonic()
    try:
        adapter.create_view_as(
            connection=connection,
            destination=destination_relation,
            sql=view_sql,
            statement_recorder=recorder,
        )
    except Exception as exc:
        return CloneItemResult(
            name=name,
            action=CloneAction.FAILED,
            status=CloneStatus.FAILED,
            message=str(exc),
            origin_relation=origin_relation,
            destination_relation=destination_relation,
            duration_seconds=time.monotonic() - start,
            executed_statements=recorder.snapshot(),
        )
    return CloneItemResult(
        name=name,
        action=CloneAction.RECREATED_VIEW,
        status=CloneStatus.SUCCESS,
        origin_relation=origin_relation,
        destination_relation=destination_relation,
        duration_seconds=time.monotonic() - start,
        executed_statements=recorder.snapshot(),
    )
