"""Source loader execution pipeline."""

from __future__ import annotations

import queue
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.executor.load.helpers.dag_runtime import (
    build_load_dag_state,
    complete_dag_source,
    execute_ready_dag_source,
    load_dag_worker,
)
from sqlbuild.executor.load.models import LoadDagState, LoadExecutionIndexes, LoadExecutionResult
from sqlbuild.executor.shared.helpers.load_execution import (
    build_load_execution_indexes,
    build_source_downstream_names,
    build_source_upstream_names,
)
from sqlbuild.spec.models.source import SourceEntry


def run_load_pipeline(
    *,
    sources: tuple[SourceEntry, ...],
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    run_id: str,
    environment: str | None,
    vars: dict[str, object],
    is_reload: bool,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    max_concurrency: int = 1,
    on_load_complete: Callable[[LoadExecutionResult], None] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
) -> tuple[LoadExecutionResult, ...]:
    """Execute selected source loaders."""

    indexes: LoadExecutionIndexes = build_load_execution_indexes(
        sources=sources,
        loader_functions=loader_functions,
    )
    source_count: int = sum(1 for source in sources if source.loader is not None)
    if source_count == 0:
        return ()
    effective_concurrency: int = max(1, min(max_concurrency, source_count))
    if on_connection_start is not None:
        on_connection_start(effective_concurrency)
    start: float = time.monotonic()
    connections: list[Any] = []
    try:
        for _ in range(effective_concurrency):
            connections.append(adapter.connect(connection_config))
    except Exception:
        if on_connection_error is not None:
            on_connection_error(effective_concurrency, time.monotonic() - start)
        connection: Any
        for connection in connections:
            adapter.close(connection)
        raise
    if on_connection_complete is not None:
        on_connection_complete(effective_concurrency, time.monotonic() - start)

    source_by_name: dict[str, SourceEntry] = {source.name: source for source in sources}
    source_index_by_name: dict[str, int] = {
        source.name: index for index, source in enumerate(sources)
    }
    upstream_names: dict[str, tuple[str, ...]] = build_source_upstream_names(
        sources=sources,
        indexes=indexes,
    )
    downstream_names: dict[str, tuple[str, ...]] = build_source_downstream_names(
        upstream_names=upstream_names
    )
    results: list[LoadExecutionResult | None] = [None] * len(sources)
    try:
        state: LoadDagState = build_load_dag_state(
            sources=sources,
            results=results,
            source_index_by_name=source_index_by_name,
            upstream_names=upstream_names,
            downstream_names=downstream_names,
        )
        connection_pool: queue.Queue[Any] = queue.Queue()
        connection: Any
        for connection in connections:
            connection_pool.put(connection)

        if effective_concurrency == 1:
            sequential_connection: Any = connections[0]
            while state.ready:
                source_name: str = state.ready.pop(0)
                complete_dag_source(
                    source_name=source_name,
                    result=execute_ready_dag_source(
                        source_name=source_name,
                        source_by_name=source_by_name,
                        indexes=indexes,
                        failed_or_skipped=state.failed_or_skipped,
                        adapter=adapter,
                        connection=sequential_connection,
                        run_id=run_id,
                        environment=environment,
                        vars=vars,
                        is_reload=is_reload,
                        start_cursor_ts=start_cursor_ts,
                        end_cursor_ts=end_cursor_ts,
                        start_cursor_int=start_cursor_int,
                        end_cursor_int=end_cursor_int,
                    ),
                    state=state,
                    on_load_complete=on_load_complete,
                )
            return tuple(result for result in results if result is not None)

        with ThreadPoolExecutor(max_workers=effective_concurrency) as pool:
            while state.ready or state.in_flight:
                while state.ready and len(state.in_flight) < effective_concurrency:
                    source_name = state.ready.pop(0)
                    state.in_flight.add(source_name)
                    pool.submit(
                        load_dag_worker,
                        source_name,
                        source_by_name,
                        indexes,
                        state.failed_or_skipped,
                        adapter,
                        connection_pool,
                        run_id,
                        environment,
                        vars,
                        is_reload,
                        start_cursor_ts,
                        end_cursor_ts,
                        start_cursor_int,
                        end_cursor_int,
                        state.completion_queue,
                    )
                if not state.in_flight:
                    break
                completed_source_name, result = state.completion_queue.get()
                state.in_flight.discard(completed_source_name)
                complete_dag_source(
                    source_name=completed_source_name,
                    result=result,
                    state=state,
                    on_load_complete=on_load_complete,
                )
        return tuple(result for result in results if result is not None)
    finally:
        connection = None
        for connection in connections:
            adapter.close(connection)
