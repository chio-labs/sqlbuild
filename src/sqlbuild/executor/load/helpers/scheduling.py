"""Load pipeline phases: external preloads, connections, and DAG scheduling."""

from __future__ import annotations

import queue
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.exceptions import ExecutorInputError
from sqlbuild.executor.helpers.load_execution import (
    build_source_downstream_names,
    build_source_upstream_names,
    dependency_node_names,
)
from sqlbuild.executor.load.helpers.dag_runtime import (
    build_load_dag_state,
    complete_dag_source,
    execute_ready_dag_source,
    load_dag_worker,
)
from sqlbuild.executor.load.models import (
    ExternalLoadPhaseResult,
    LoadCallbacks,
    LoadDagState,
    LoadDispatchInputs,
    LoadExecutionIndexes,
    LoadExecutionResult,
    LoadRuntimeParams,
)
from sqlbuild.executor.load.types import LoadProgressCallback
from sqlbuild.shared.types import ConnectionElapsedCallback
from sqlbuild.spec.models.source import SourceEntry


def validate_external_loaders_are_preconnect_runnable(
    *, sources: tuple[SourceEntry, ...], indexes: LoadExecutionIndexes
) -> None:
    """Reject external loaders that depend on SQLBuild-connection loaders."""

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


def run_external_source_loads(
    *,
    sources: tuple[SourceEntry, ...],
    indexes: LoadExecutionIndexes,
    source_by_name: dict[str, SourceEntry],
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    runtime: LoadRuntimeParams,
    callbacks: LoadCallbacks,
) -> ExternalLoadPhaseResult:
    """Run external-connection loaders before opening warehouse connections."""

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
    on_load_progress: LoadProgressCallback | None = callbacks.on_load_progress
    external_source: SourceEntry
    for external_source in external_sources:
        if callbacks.on_load_start is not None:
            callbacks.on_load_start(external_source)
        result: LoadExecutionResult = execute_ready_dag_source(
            source_name=external_source.name,
            dispatch=LoadDispatchInputs(
                source_by_name=source_by_name,
                indexes=indexes,
                failed_or_hard_skipped=failed_or_hard_skipped,
                results_by_name={},
            ),
            adapter=adapter,
            connection_config=connection_config,
            connection=None,
            runtime=runtime,
            on_progress=(
                None
                if on_load_progress is None
                else lambda message, source=external_source: on_load_progress(
                    source, message=message
                )
            ),
        )
        preloaded_results.append(result)
        if result.status.value == "failed" or (
            result.status.value == "skipped" and result.skip_mode == SkipMode.HARD
        ):
            failed_or_hard_skipped.add(external_source.name)
        if callbacks.on_load_complete is not None:
            callbacks.on_load_complete(result)
    return ExternalLoadPhaseResult(
        preloaded_results=tuple(preloaded_results),
        failed_or_hard_skipped=frozenset(failed_or_hard_skipped),
        sqlbuild_sources=sqlbuild_sources,
    )


def open_load_connections(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    effective_concurrency: int,
    on_connection_start: Callable[[int], None] | None,
    on_connection_complete: ConnectionElapsedCallback | None,
    on_connection_error: ConnectionElapsedCallback | None,
) -> tuple[Any, ...]:
    """Open one warehouse connection per worker with progress callbacks."""

    if on_connection_start is not None:
        on_connection_start(effective_concurrency)
    start: float = time.monotonic()
    connections: list[Any] = []
    try:
        for _ in range(effective_concurrency):
            connections.append(adapter.connect(connection_config))
    except Exception:
        if on_connection_error is not None:
            on_connection_error(effective_concurrency, elapsed_seconds=time.monotonic() - start)
        connection: Any
        for connection in connections:
            adapter.close(connection)
        raise
    if on_connection_complete is not None:
        on_connection_complete(effective_concurrency, elapsed_seconds=time.monotonic() - start)
    return tuple(connections)


def run_load_dag(
    *,
    sqlbuild_sources: tuple[SourceEntry, ...],
    source_by_name: dict[str, SourceEntry],
    indexes: LoadExecutionIndexes,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connections: tuple[Any, ...],
    effective_concurrency: int,
    initial_failed_or_hard_skipped: frozenset[str],
    runtime: LoadRuntimeParams,
    callbacks: LoadCallbacks,
) -> tuple[LoadExecutionResult, ...]:
    """Execute the SQLBuild-connection loader DAG sequentially or concurrently."""

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
    state: LoadDagState = build_load_dag_state(
        sources=sqlbuild_sources,
        results=results,
        source_index_by_name=source_index_by_name,
        upstream_names=upstream_names,
        downstream_names=downstream_names,
    )
    state.failed_or_skipped.update(initial_failed_or_hard_skipped)
    if effective_concurrency == 1:
        _run_sequential_load_dag(
            state=state,
            source_by_name=source_by_name,
            indexes=indexes,
            adapter=adapter,
            connection_config=connection_config,
            connection=connections[0],
            runtime=runtime,
            callbacks=callbacks,
        )
    else:
        _run_concurrent_load_dag(
            state=state,
            source_by_name=source_by_name,
            indexes=indexes,
            adapter=adapter,
            connection_config=connection_config,
            connections=connections,
            effective_concurrency=effective_concurrency,
            runtime=runtime,
            callbacks=callbacks,
        )
    return tuple(result for result in results if result is not None)


def _run_sequential_load_dag(
    *,
    state: LoadDagState,
    source_by_name: dict[str, SourceEntry],
    indexes: LoadExecutionIndexes,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    runtime: LoadRuntimeParams,
    callbacks: LoadCallbacks,
) -> None:
    while state.ready:
        source_name: str = state.pop_next_ready()
        _ = complete_dag_source(
            source_name=source_name,
            result=execute_ready_dag_source(
                source_name=source_name,
                dispatch=LoadDispatchInputs(
                    source_by_name=source_by_name,
                    indexes=indexes,
                    failed_or_hard_skipped=state.failed_or_skipped,
                    results_by_name=state.results_by_name,
                ),
                adapter=adapter,
                connection_config=connection_config,
                connection=connection,
                runtime=runtime,
            ),
            state=state,
            on_load_complete=callbacks.on_load_complete,
        )


def _run_concurrent_load_dag(
    *,
    state: LoadDagState,
    source_by_name: dict[str, SourceEntry],
    indexes: LoadExecutionIndexes,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connections: tuple[Any, ...],
    effective_concurrency: int,
    runtime: LoadRuntimeParams,
    callbacks: LoadCallbacks,
) -> None:
    connection_pool: queue.Queue[Any] = queue.Queue()
    connection: Any
    for connection in connections:
        connection_pool.put(connection)
    with ThreadPoolExecutor(max_workers=effective_concurrency) as pool:
        while state.ready or state.in_flight:
            while state.ready and len(state.in_flight) < effective_concurrency:
                source_name: str = state.pop_next_ready()
                state.mark_in_flight(source_name)
                if callbacks.on_load_start is not None:
                    callbacks.on_load_start(source_by_name[source_name])
                pool.submit(
                    lambda name=source_name: load_dag_worker(
                        source_name=name,
                        dispatch=LoadDispatchInputs(
                            source_by_name=source_by_name,
                            indexes=indexes,
                            failed_or_hard_skipped=state.failed_or_skipped,
                            results_by_name=state.results_by_name,
                        ),
                        adapter=adapter,
                        connection_config=connection_config,
                        connection_pool=connection_pool,
                        runtime=runtime,
                        completion_queue=state.completion_queue,
                        on_load_progress=callbacks.on_load_progress,
                    )
                )
            if not state.in_flight:
                break
            completed_source_name, result = state.completion_queue.get()
            state.finish_in_flight(completed_source_name)
            _ = complete_dag_source(
                source_name=completed_source_name,
                result=result,
                state=state,
                on_load_complete=callbacks.on_load_complete,
            )
