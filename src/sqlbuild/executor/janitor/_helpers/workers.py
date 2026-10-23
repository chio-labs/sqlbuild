"""Size and open the extra warehouse connections of concurrent janitor actions."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.janitor.models import JanitorPlan
from sqlbuild.executor.janitor.types import JanitorConnectionProgress
from sqlbuild.executor.pipeline.main._open_worker_connection_pool import (
    open_worker_connection_pool,
)
from sqlbuild.executor.pipeline.main.raise_warehouse_connection_failure import (
    raise_warehouse_connection_failure,
)


def janitor_worker_count(*, plan: JanitorPlan, adapter: BaseAdapter, concurrency: int) -> int:
    """Connections the largest phase can use: the concurrency, capped by the adapter's DDL limit."""

    largest_phase: int = max(
        0 if plan.direct_mode else len(plan.candidates),
        len(plan.archive_candidates) if plan.direct_mode else 0,
        len(plan.archive_deletion_candidates) if plan.direct_mode else 0,
        len(plan.old_name_views.drops) + len(plan.old_name_views.missing),
        len(plan.query_diff_artifact_candidates),
        len(plan.direct_state_prune_candidates),
    )
    return max(1, min(concurrency, int(adapter.concurrent_ddl_limit), largest_phase))


def open_janitor_worker_connections(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object] | None,
    count: int,
    progress: JanitorConnectionProgress | None,
) -> tuple[Any, ...]:
    """Open `count` extra connections, reporting the connect phase to `progress`."""

    if count <= 0 or connection_config is None:
        return ()
    if progress is not None:
        progress.on_connection_start(count)
    started: float = time.monotonic()
    try:
        connections: tuple[Any, ...] = open_worker_connection_pool(
            adapter=adapter, connection_config=connection_config, connection_count=count
        )
    except BaseException as error:
        if progress is not None:
            progress.on_connection_error(
                connection_count=count, elapsed_seconds=time.monotonic() - started
            )
        raise_warehouse_connection_failure(adapter=adapter, error=error)
    if progress is not None:
        progress.on_connection_complete(
            connection_count=count, elapsed_seconds=time.monotonic() - started
        )
    return connections
