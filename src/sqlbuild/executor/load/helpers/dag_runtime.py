"""Concurrent DAG helpers for source loader execution."""

from __future__ import annotations

import queue
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.executor.load.main.execute import execute_source_load
from sqlbuild.executor.load.models import LoadDagState, LoadExecutionIndexes, LoadExecutionResult
from sqlbuild.executor.shared.helpers.load_execution import (
    should_skip_due_to_failed_dependency,
    skipped_load_result,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.spec.models.source import SourceEntry


def build_load_dag_state(
    *,
    sources: tuple[SourceEntry, ...],
    results: list[LoadExecutionResult | None],
    source_index_by_name: dict[str, int],
    upstream_names: dict[str, tuple[str, ...]],
    downstream_names: dict[str, tuple[str, ...]],
) -> LoadDagState:
    """Build mutable state for concurrent source-loader DAG execution."""

    in_degree: dict[str, int] = {
        source.name: len(upstream_names[source.name]) for source in sources
    }
    ready: list[str] = [source.name for source in sources if in_degree[source.name] == 0]
    return LoadDagState(
        results=results,
        in_degree=in_degree,
        ready=ready,
        in_flight=set(),
        failed_or_skipped=set(),
        source_index_by_name=source_index_by_name,
        downstream_names=downstream_names,
        completion_queue=queue.Queue(),
    )


def complete_dag_source(
    *,
    source_name: str,
    result: LoadExecutionResult,
    state: LoadDagState,
    on_load_complete: Callable[[LoadExecutionResult], None] | None,
) -> None:
    """Record one completed source-loader node and unlock downstream nodes."""

    source_index: int = state.source_index_by_name[source_name]
    state.results[source_index] = result
    if result.status != ExecutionStatus.SUCCESS:
        state.failed_or_skipped.add(source_name)
    if on_load_complete is not None:
        on_load_complete(result)
    downstream_name: str
    for downstream_name in state.downstream_names.get(source_name, ()):
        state.in_degree[downstream_name] = state.in_degree.get(downstream_name, 1) - 1
        if state.in_degree[downstream_name] == 0:
            state.ready.append(downstream_name)


def execute_ready_dag_source(
    *,
    source_name: str,
    source_by_name: dict[str, SourceEntry],
    indexes: LoadExecutionIndexes,
    failed_or_skipped: set[str],
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    environment: str | None,
    vars: dict[str, object],
    is_reload: bool,
    start_cursor_ts: datetime | None,
    end_cursor_ts: datetime | None,
    start_cursor_int: int | None,
    end_cursor_int: int | None,
) -> LoadExecutionResult:
    """Execute one ready DAG node or return a skipped result."""

    source: SourceEntry = source_by_name[source_name]
    if should_skip_due_to_failed_dependency(
        source=source,
        failed_or_skipped=failed_or_skipped,
        indexes=indexes,
    ):
        return skipped_load_result(source)
    return execute_source_load(
        source_entry=source,
        loader_function=indexes.loader_by_name[source.loader or ""],
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        environment=environment,
        vars=vars,
        is_reload=is_reload,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
        statement_recorder=StatementRecorder(),
        loader_ref_entries=indexes.loader_ref_entries,
        source_ref_entries=indexes.source_by_name,
    )


def load_dag_worker(
    source_name: str,
    source_by_name: dict[str, SourceEntry],
    indexes: LoadExecutionIndexes,
    failed_or_skipped: set[str],
    adapter: BaseAdapter,
    connection_pool: queue.Queue[Any],
    run_id: str,
    environment: str | None,
    vars: dict[str, object],
    is_reload: bool,
    start_cursor_ts: datetime | None,
    end_cursor_ts: datetime | None,
    start_cursor_int: int | None,
    end_cursor_int: int | None,
    completion_queue: queue.Queue[tuple[str, LoadExecutionResult]],
) -> None:
    """Worker wrapper for concurrent DAG source-loader execution."""

    connection: Any = connection_pool.get()
    try:
        completion_queue.put(
            (
                source_name,
                execute_ready_dag_source(
                    source_name=source_name,
                    source_by_name=source_by_name,
                    indexes=indexes,
                    failed_or_skipped=failed_or_skipped,
                    adapter=adapter,
                    connection=connection,
                    run_id=run_id,
                    environment=environment,
                    vars=vars,
                    is_reload=is_reload,
                    start_cursor_ts=start_cursor_ts,
                    end_cursor_ts=end_cursor_ts,
                    start_cursor_int=start_cursor_int,
                    end_cursor_int=end_cursor_int,
                ),
            )
        )
    finally:
        connection_pool.put(connection)
