"""Test execution pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import PlanOutput, SqlTestPlanEntry
from sqlbuild.executor.testing.main.execute import execute_sql_test
from sqlbuild.executor.testing.models import SqlTestExecutionResult


def run_test_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    on_test_complete: Callable[[SqlTestExecutionResult], None] | None = None,
) -> tuple[SqlTestExecutionResult, ...]:
    """Execute all SQL unit tests from a compiled plan."""

    connection: Any = adapter.connect(connection_config)
    try:
        results: list[SqlTestExecutionResult] = []
        entry: SqlTestPlanEntry
        for entry in plan.test_entries:
            result: SqlTestExecutionResult = execute_sql_test(
                test_entry=entry, adapter=adapter, connection=connection
            )
            results.append(result)
            if on_test_complete is not None:
                on_test_complete(result)
        return tuple(results)
    finally:
        adapter.close(connection)
