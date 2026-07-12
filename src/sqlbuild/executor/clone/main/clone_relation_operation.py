"""Shared physical clone operation over already-resolved relation names."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.clone.models import CloneItemResult
from sqlbuild.executor.clone.types import CloneAction, CloneStatus


def clone_relation_by_names(
    *,
    name: str,
    origin_relation: str,
    destination_relation: str,
    origin_exists: bool,
    adapter: BaseAdapter,
    connection: Any,
    hard_copy: bool,
    origin_is_transient: bool = False,
) -> CloneItemResult:
    """Drop then clone or copy origin into destination, returning a timed item result."""

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
        adapter.drop(
            connection=connection,
            destination=destination_relation,
            if_exists=True,
            statement_recorder=recorder,
        )
        adapter.clone(
            connection=connection,
            origin=origin_relation,
            destination=destination_relation,
            hard_copy=hard_copy,
            origin_is_transient=origin_is_transient,
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
    action: CloneAction = (
        CloneAction.COPIED
        if hard_copy or not adapter.supports_zero_copy_clone()
        else CloneAction.CLONED
    )
    return CloneItemResult(
        name=name,
        action=action,
        status=CloneStatus.SUCCESS,
        origin_relation=origin_relation,
        destination_relation=destination_relation,
        duration_seconds=time.monotonic() - start,
        executed_statements=recorder.snapshot(),
    )
