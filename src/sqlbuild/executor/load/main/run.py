"""Source loader execution pipeline."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.executor.helpers.load_execution import build_load_execution_indexes
from sqlbuild.executor.load.helpers.scheduling import (
    open_load_connections,
    run_external_source_loads,
    run_load_dag,
    validate_external_loaders_are_preconnect_runnable,
)
from sqlbuild.executor.load.models import (
    ExternalLoadPhaseResult,
    LoadCallbacks,
    LoadExecutionIndexes,
    LoadExecutionResult,
    LoadRuntimeParams,
)
from sqlbuild.spec.models.source import SourceEntry


def run_load_pipeline(
    *,
    sources: tuple[SourceEntry, ...],
    reference_sources: tuple[SourceEntry, ...] = (),
    loader_functions: tuple[DiscoveredLoaderFunction, ...],
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    runtime: LoadRuntimeParams,
    callbacks: LoadCallbacks | None = None,
    max_concurrency: int = 1,
) -> tuple[LoadExecutionResult, ...]:
    """Execute selected source loaders."""

    resolved_callbacks: LoadCallbacks = callbacks if callbacks is not None else LoadCallbacks()
    index_sources: tuple[SourceEntry, ...] = (*sources, *reference_sources)
    indexes: LoadExecutionIndexes = build_load_execution_indexes(
        sources=index_sources,
        loader_functions=loader_functions,
    )
    source_count: int = sum(1 for source in sources if source.loader is not None)
    if source_count == 0:
        return ()
    validate_external_loaders_are_preconnect_runnable(sources=sources, indexes=indexes)
    source_by_name: dict[str, SourceEntry] = {source.name: source for source in index_sources}
    external_phase: ExternalLoadPhaseResult = run_external_source_loads(
        sources=sources,
        indexes=indexes,
        source_by_name=source_by_name,
        adapter=adapter,
        connection_config=connection_config,
        runtime=runtime,
        callbacks=resolved_callbacks,
    )
    if not external_phase.sqlbuild_sources:
        return external_phase.preloaded_results

    remaining_source_count: int = sum(
        1 for source in external_phase.sqlbuild_sources if source.loader is not None
    )
    effective_concurrency: int = max(1, min(max_concurrency, remaining_source_count))
    connections: tuple[Any, ...] = open_load_connections(
        adapter=adapter,
        connection_config=connection_config,
        effective_concurrency=effective_concurrency,
        on_connection_start=resolved_callbacks.on_connection_start,
        on_connection_complete=resolved_callbacks.on_connection_complete,
        on_connection_error=resolved_callbacks.on_connection_error,
    )
    try:
        dag_results: tuple[LoadExecutionResult, ...] = run_load_dag(
            sqlbuild_sources=external_phase.sqlbuild_sources,
            source_by_name=source_by_name,
            indexes=indexes,
            adapter=adapter,
            connection_config=connection_config,
            connections=connections,
            effective_concurrency=effective_concurrency,
            initial_failed_or_hard_skipped=external_phase.failed_or_hard_skipped,
            runtime=runtime,
            callbacks=resolved_callbacks,
        )
    finally:
        connection: Any
        for connection in connections:
            adapter.close(connection)
    return external_phase.preloaded_results + dag_results
