"""Integration coverage for grouped microbatch reconciliation row counts."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.executor.run._helpers.materializations.microbatch import (
    _count_unaccounted_intervals,
)
from sqlbuild.executor.run.models import (
    MicrobatchLifecycleState,
    MicrobatchTargets,
    ModelExecutionResult,
    ModelMaterializationContext,
)
from sqlbuild.microbatches.models import MicrobatchInterval
from tests.integration.src.sqlbuild.executor.run.microbatch._test_types import (
    MicrobatchReconciliationChunkTestCase,
)
from tests.integration.src.sqlbuild.executor.run.microbatch.helpers import (
    build_integer_reconciliation_plan_entry,
)


class _CountTrackingDuckDbAdapter(DuckDbAdapter):
    def __init__(self) -> None:
        self.count_sqls: list[str] = []

    def execute(self, *, connection: Any, sql: str) -> Any:
        if "AS __sqb_count_" in sql:
            self.count_sqls.append(sql)
        return super().execute(connection=connection, sql=sql)


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchReconciliationChunkTestCase(
            description="one full chunk uses one grouped query",
            interval_count=100,
            occupied_values=(0, 99),
            expected_query_count=1,
        ),
        MicrobatchReconciliationChunkTestCase(
            description="one interval beyond boundary starts a second grouped query",
            interval_count=101,
            occupied_values=(99, 100),
            expected_query_count=2,
        ),
        MicrobatchReconciliationChunkTestCase(
            description="two full chunks plus one interval use three grouped queries",
            interval_count=201,
            occupied_values=(99, 100, 199, 200),
            expected_query_count=3,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_many_unaccounted_intervals_when_counting_then_queries_are_chunked_without_n_plus_one(
    test_case: MicrobatchReconciliationChunkTestCase,
) -> None:
    adapter: _CountTrackingDuckDbAdapter = _CountTrackingDuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        connection.execute("CREATE TABLE main.orders (id INTEGER)")
        values_sql: str = ", ".join(f"({value})" for value in test_case.occupied_values)
        connection.execute(f"INSERT INTO main.orders VALUES {values_sql}")
        context: ModelMaterializationContext = ModelMaterializationContext(
            entry=build_integer_reconciliation_plan_entry(),
            adapter=adapter,
            connection=connection,
            model_locations={},
            seed_locations={},
            source_map={},
            model_audits=(),
            run_id="reconciliation-chunks",
            query_change_tracking=False,
        )
        intervals: tuple[MicrobatchInterval, ...] = tuple(
            MicrobatchInterval(start=str(value), end=str(value + 1))
            for value in range(test_case.interval_count)
        )

        result: dict[tuple[str, str], int] | ModelExecutionResult = _count_unaccounted_intervals(
            context=context,
            state=MicrobatchLifecycleState(
                warnings=[],
                audit_results=[],
                hook_results=[],
                statement_recorder=StatementRecorder(),
            ),
            targets=MicrobatchTargets(
                target_database=None,
                target_schema="main",
                target_table="orders",
                target_qualified="main.orders",
                delta_table="orders__delta",
                delta_qualified="main.orders__delta",
            ),
            intervals=intervals,
        )
    finally:
        adapter.close(connection)

    assert isinstance(result, dict)
    assert len(result) == test_case.interval_count
    assert len(adapter.count_sqls) == test_case.expected_query_count
    assert all(sql.count("AS __sqb_count_") <= 100 for sql in adapter.count_sqls)
    assert all("AS __sqb_count_0" in sql for sql in adapter.count_sqls)
    occupied: set[int] = set(test_case.occupied_values)
    assert result == {
        (str(value), str(value + 1)): int(value in occupied)
        for value in range(test_case.interval_count)
    }


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
