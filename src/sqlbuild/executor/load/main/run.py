"""Source loader execution pipeline."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
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
from sqlbuild.executor.shared.helpers.load_execution import build_load_execution_indexes
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
    validate_external_loaders_are_preconnect_runnable(sources=sources, indexes=indexes)
    runtime: LoadRuntimeParams = LoadRuntimeParams(
        run_id=run_id,
        target=target,
        vars=vars,
        is_reload=is_reload,
        runtime_dir=runtime_dir,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
        use_color=use_color,
        providers=providers,
        result_store=result_store,
    )
    callbacks: LoadCallbacks = LoadCallbacks(
        on_load_start=on_load_start,
        on_load_progress=on_load_progress,
        on_load_complete=on_load_complete,
    )
    source_by_name: dict[str, SourceEntry] = {source.name: source for source in index_sources}
    external_phase: ExternalLoadPhaseResult = run_external_source_loads(
        sources=sources,
        indexes=indexes,
        source_by_name=source_by_name,
        adapter=adapter,
        connection_config=connection_config,
        runtime=runtime,
        callbacks=callbacks,
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
        on_connection_start=on_connection_start,
        on_connection_complete=on_connection_complete,
        on_connection_error=on_connection_error,
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
            callbacks=callbacks,
        )
    finally:
        connection: Any
        for connection in connections:
            adapter.close(connection)
    return external_phase.preloaded_results + dag_results
