"""Seed execution pipeline."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import PlanOutput, SeedPlanEntry
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.seed.main.execute import execute_seed
from sqlbuild.shared.types import ConnectionElapsedCallback


def run_seed_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    max_concurrency: int = 1,
    run_id: str = "",
    query_change_tracking: bool = False,
    on_seed_complete: Callable[[SeedExecutionResult], None] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: ConnectionElapsedCallback | None = None,
    on_connection_error: ConnectionElapsedCallback | None = None,
) -> tuple[SeedExecutionResult, ...]:
    """Execute all seed loads from a compiled plan."""

    seed_entries: tuple[SeedPlanEntry, ...] = plan.seed_entries
    if not seed_entries:
        return ()
    effective_concurrency: int = max(1, min(max_concurrency, len(seed_entries)))
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

    results: list[SeedExecutionResult | None] = [None] * len(seed_entries)
    try:

        def run_worker(worker_index: int) -> None:
            seed_index: int
            entry: SeedPlanEntry
            for seed_index, entry in enumerate(seed_entries):
                if seed_index % effective_concurrency != worker_index:
                    continue
                result: SeedExecutionResult = execute_seed(
                    seed_entry=entry,
                    adapter=adapter,
                    connection=connections[worker_index],
                    statement_recorder=StatementRecorder(),
                    run_id=run_id,
                    query_change_tracking=query_change_tracking,
                )
                results[seed_index] = result
                if on_seed_complete is not None:
                    on_seed_complete(result)

        with ThreadPoolExecutor(max_workers=effective_concurrency) as pool:
            list(pool.map(run_worker, range(effective_concurrency)))
        return tuple(result for result in results if result is not None)
    finally:
        connection = None
        for connection in connections:
            adapter.close(connection)
