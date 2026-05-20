"""Source loader execution pipeline."""

from __future__ import annotations

from collections.abc import Callable
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
    on_load_complete: Callable[[LoadExecutionResult], None] | None = None,
) -> tuple[LoadExecutionResult, ...]:
    """Execute selected source loaders."""

    loader_map: dict[str, DiscoveredLoaderFunction] = {
        loader.name: loader for loader in loader_functions
    }
    connection: Any = adapter.connect(connection_config)
    try:
        results: list[LoadExecutionResult] = []
        source: SourceEntry
        for source in sources:
            if source.loader is None:
                continue
            result: LoadExecutionResult = execute_source_load(
                source_entry=source,
                loader_function=loader_map[source.loader],
                adapter=adapter,
                connection=connection,
                run_id=run_id,
                environment=environment,
                vars=vars,
                is_reload=is_reload,
                statement_recorder=StatementRecorder(),
            )
            results.append(result)
            if on_load_complete is not None:
                on_load_complete(result)
        return tuple(results)
    finally:
        adapter.close(connection)
