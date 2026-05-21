"""Source loader execution pipeline."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.executor.load.main.execute import execute_source_load
from sqlbuild.executor.load.models import LoadExecutionResult
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

    loader_map: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in loader_functions
    }
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

    results: list[LoadExecutionResult | None] = [None] * len(sources)
    try:

        def run_worker(worker_index: int) -> None:
            source_index: int
            source: SourceEntry
            for source_index, source in enumerate(sources):
                if source_index % effective_concurrency != worker_index:
                    continue
                if source.loader is None:
                    continue
                result: LoadExecutionResult = execute_source_load(
                    source_entry=source,
                    loader_function=loader_map[source.loader],
                    adapter=adapter,
                    connection=connections[worker_index],
                    run_id=run_id,
                    environment=environment,
                    vars=vars,
                    is_reload=is_reload,
                    start_cursor_ts=start_cursor_ts,
                    end_cursor_ts=end_cursor_ts,
                    start_cursor_int=start_cursor_int,
                    end_cursor_int=end_cursor_int,
                    statement_recorder=StatementRecorder(),
                )
                results[source_index] = result
                if on_load_complete is not None:
                    on_load_complete(result)

        with ThreadPoolExecutor(max_workers=effective_concurrency) as pool:
            list(pool.map(run_worker, range(effective_concurrency)))
        return tuple(result for result in results if result is not None)
    finally:
        connection = None
        for connection in connections:
            adapter.close(connection)
