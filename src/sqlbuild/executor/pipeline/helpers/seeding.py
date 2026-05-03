"""Seed execution pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import PlanOutput, SeedPlanEntry
from sqlbuild.executor.build.models import SeedExecutionResult
from sqlbuild.executor.seed.main.execute import execute_seed


def run_seed_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    on_seed_complete: Callable[[SeedExecutionResult], None] | None = None,
) -> tuple[SeedExecutionResult, ...]:
    """Execute all seed loads from a compiled plan."""

    connection: Any = adapter.connect(connection_config)
    try:
        results: list[SeedExecutionResult] = []
        entry: SeedPlanEntry
        for entry in plan.seed_entries:
            result: SeedExecutionResult = execute_seed(
                seed_entry=entry,
                adapter=adapter,
                connection=connection,
                statement_recorder=StatementRecorder(),
            )
            results.append(result)
            if on_seed_complete is not None:
                on_seed_complete(result)
        return tuple(results)
    finally:
        adapter.close(connection)
