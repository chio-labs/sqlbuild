"""Relation reuse materialization helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.shared.exceptions import ExecutorInputError


def create_relation_from_reuse_origin(
    *,
    adapter: BaseAdapter,
    connection: Any,
    origin_relation: str,
    destination_relation: str,
    hard_copy: bool,
    statement_recorder: StatementRecorder,
) -> None:
    """Create a destination relation from the configured reuse origin relation."""

    if hard_copy:
        adapter.durable_clone(
            connection,
            origin=origin_relation,
            destination=destination_relation,
            statement_recorder=statement_recorder,
        )
        return
    if not adapter.supports_zero_copy_clone():
        raise ExecutorInputError(
            f"adapter '{adapter.adapter_name}' does not support cheap relation reuse. "
            "Set reuse_hard_copy = true for this target to force copy-based reuse, "
            "or remove reuse_from to build normally."
        )
    adapter.clone(
        connection,
        origin=origin_relation,
        destination=destination_relation,
        hard_copy=False,
        statement_recorder=statement_recorder,
    )
