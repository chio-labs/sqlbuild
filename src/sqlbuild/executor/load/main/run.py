"""Source loader execution pipeline."""

from __future__ import annotations

import queue
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.load.helpers.dag_runtime import (
    build_load_dag_state,
    complete_dag_source,
    execute_ready_dag_source,
    load_dag_worker,
)
from sqlbuild.executor.load.models import LoadDagState, LoadExecutionIndexes, LoadExecutionResult
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.helpers.load_execution import (
    build_load_execution_indexes,
    build_source_downstream_names,
    build_source_upstream_names,
    dependency_node_names,
)
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.spec.models.source import SourceEntry


def run_load_pipeline(
    *,
    sources: tuple[SourceEntry, ...],
    reference_sources: tuple[SourceEntry, ...] = (),
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    run_id: str,
    runtime_dir: Path = Path("target"),
    target: str | None,
    vars: dict[str, object],
    is_reload: bool,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    max_concurrency: int = 1,
    on_load_start: Callable[[SourceEntry], None] | None = None,
    on_load_progress: Callable[[SourceEntry, str], None] | None = None,
    on_load_complete: Callable[[LoadExecutionResult], None] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
    use_color: bool = False,
    providers: ProviderContainer | None = None,
    result_store: Any | None = None,
) -> tuple[LoadExecutionResult, ...]:
    """Execute selected source loaders."""

    index_sources: tuple[SourceEntry, ...] = (*sources, *reference_sources)
    indexes: LoadExecutionIndexes = build_load_execution_indexes(
        sources=index_sources,
        loader_functions=loader_functions,
    )
    source_count: int = sum(1 for source in sources if source.loader is not None)
    if source_count == 0:
        return ()
    _validate_external_loaders_are_preconnect_runnable(sources=sources, indexes=indexes)
    external_sources: tuple[SourceEntry, ...] = tuple(
        source
        for source in sources
        if source.loader is not None
        and indexes.loader_by_name[source.loader].connection_mode == LoaderConnectionMode.EXTERNAL
    )
    sqlbuild_sources: tuple[SourceEntry, ...] = tuple(
        source
        for source in sources
        if source.loader is None
        or indexes.loader_by_name[source.loader].connection_mode == LoaderConnectionMode.SQLBUILD
    )
    preloaded_results: list[LoadExecutionResult] = []
    failed_or_hard_skipped: set[str] = set()
    source_by_name: dict[str, SourceEntry] = {source.name: source for source in index_sources}
    external_source: SourceEntry
    for external_source in external_sources:
        if on_load_start is not None:
            on_load_start(external_source)
        result: LoadExecutionResult = execute_ready_dag_source(
            source_name=external_source.name,
            source_by_name=source_by_name,
            indexes=indexes,
            failed_or_hard_skipped=failed_or_hard_skipped,
            results_by_name={},
            adapter=adapter,
            connection_config=connection_config,
            connection=None,
            run_id=run_id,
            runtime_dir=runtime_dir,
            target=target,
            vars=vars,
            is_reload=is_reload,
            start_cursor_ts=start_cursor_ts,
            end_cursor_ts=end_cursor_ts,
            start_cursor_int=start_cursor_int,
            end_cursor_int=end_cursor_int,
            use_color=use_color,
            on_progress=(
                None
                if on_load_progress is None
                else lambda message, source=external_source: on_load_progress(source, message)
            ),
            providers=providers,
            result_store=result_store,
        )
        preloaded_results.append(result)
        if result.status.value == "failed" or (
            result.status.value == "skipped" and result.skip_mode == SkipMode.HARD
        ):
            failed_or_hard_skipped.add(external_source.name)
        if on_load_complete is not None:
            on_load_complete(result)
    if not sqlbuild_sources:
        return tuple(preloaded_results)

    remaining_source_count: int = sum(1 for source in sqlbuild_sources if source.loader is not None)
    effective_concurrency: int = max(1, min(max_concurrency, remaining_source_count))
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

    source_index_by_name: dict[str, int] = {
        source.name: index for index, source in enumerate(sqlbuild_sources)
    }
    upstream_names: dict[str, tuple[str, ...]] = build_source_upstream_names(
        sources=sqlbuild_sources,
        indexes=indexes,
    )
    downstream_names: dict[str, tuple[str, ...]] = build_source_downstream_names(
        upstream_names=upstream_names
    )
    results: list[LoadExecutionResult | None] = [None] * len(sqlbuild_sources)
    try:
        state: LoadDagState = build_load_dag_state(
            sources=sqlbuild_sources,
            results=results,
            source_index_by_name=source_index_by_name,
            upstream_names=upstream_names,
            downstream_names=downstream_names,
        )
        state.failed_or_skipped.update(failed_or_hard_skipped)
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
                        failed_or_hard_skipped=state.failed_or_skipped,
                        results_by_name=state.results_by_name,
                        adapter=adapter,
                        connection_config=connection_config,
                        connection=sequential_connection,
                        run_id=run_id,
                        runtime_dir=runtime_dir,
                        target=target,
                        vars=vars,
                        is_reload=is_reload,
                        start_cursor_ts=start_cursor_ts,
                        end_cursor_ts=end_cursor_ts,
                        start_cursor_int=start_cursor_int,
                        end_cursor_int=end_cursor_int,
                        use_color=use_color,
                        providers=providers,
                        result_store=result_store,
                    ),
                    state=state,
                    on_load_complete=on_load_complete,
                )
            return tuple(preloaded_results) + tuple(
                result for result in results if result is not None
            )

        with ThreadPoolExecutor(max_workers=effective_concurrency) as pool:
            while state.ready or state.in_flight:
                while state.ready and len(state.in_flight) < effective_concurrency:
                    source_name = state.ready.pop(0)
                    state.in_flight.add(source_name)
                    if on_load_start is not None:
                        on_load_start(source_by_name[source_name])
                    pool.submit(
                        load_dag_worker,
                        source_name,
                        source_by_name,
                        indexes,
                        state.failed_or_skipped,
                        state.results_by_name,
                        adapter,
                        connection_config,
                        connection_pool,
                        run_id,
                        target,
                        vars,
                        is_reload,
                        start_cursor_ts,
                        end_cursor_ts,
                        start_cursor_int,
                        end_cursor_int,
                        use_color,
                        state.completion_queue,
                        on_load_progress,
                        providers,
                        result_store,
                        runtime_dir,
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
        return tuple(preloaded_results) + tuple(result for result in results if result is not None)
    finally:
        connection = None
        for connection in connections:
            adapter.close(connection)


def _validate_external_loaders_are_preconnect_runnable(
    *, sources: tuple[SourceEntry, ...], indexes: LoadExecutionIndexes
) -> None:
    source_by_name: dict[str, SourceEntry] = {source.name: source for source in sources}
    source: SourceEntry
    for source in sources:
        if source.loader is None:
            continue
        loader: DiscoveredLoaderFunction = indexes.loader_by_name[source.loader]
        if loader.connection_mode != LoaderConnectionMode.EXTERNAL:
            continue
        dependency_name: str
        for dependency_name in dependency_node_names(source=source, indexes=indexes):
            dependency_source: SourceEntry | None = source_by_name.get(dependency_name)
            if dependency_source is None or dependency_source.loader is None:
                continue
            dependency_loader: DiscoveredLoaderFunction = indexes.loader_by_name[
                dependency_source.loader
            ]
            if dependency_loader.connection_mode == LoaderConnectionMode.SQLBUILD:
                raise ExecutorInputError(
                    f"External loader '{loader.name}' cannot depend on SQLBuild-connection "
                    f"loader '{dependency_loader.name}'. External loaders must be runnable "
                    "before SQLBuild opens warehouse connections."
                )
