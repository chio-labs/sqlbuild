"""Run one unit test's comparison against its actual outputs and collect step results."""

from __future__ import annotations

from typing import Any

from sqlbuild._native import SqlTestPlanEntry, render_sql_test_comparison_sql
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.testing._helpers.difference_samples import add_difference_samples
from sqlbuild.executor.testing.classes.sql_test_actual_outputs import SqlTestActualOutputs
from sqlbuild.executor.testing.models import StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome


def compare_actual_outputs(
    *,
    test_entry: SqlTestPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    inline_sql: str,
    outputs: SqlTestActualOutputs,
) -> list[StepResult]:
    """Store the actual outputs once where supported, then count and sample the differences."""

    relations: dict[int, str] = outputs.materialize()
    comparison_sql: str = inline_sql
    if relations:
        (comparison_sql,) = render_sql_test_comparison_sql(
            (test_entry,),
            set_difference_operator=adapter.render_set_difference_operator(),
            sql_analysis_dialect=adapter.sql_analysis_dialect(),
            actual_relations=relations,
        )
    cursor: Any = adapter.execute(connection=connection, sql=comparison_sql)
    rows: list[Any] = cursor.fetchall()
    return add_difference_samples(
        step_results=_build_step_results(rows),
        test_entry=test_entry,
        adapter=adapter,
        connection=connection,
        relations=relations,
    )


def _build_step_results(rows: list[Any]) -> list[StepResult]:
    """Convert comparison query rows into per-model step results."""

    step_results: list[StepResult] = []
    row: Any
    for row in sorted(rows, key=lambda item: int(item[0])):
        model_name: str = str(row[1])
        actual_count: int = int(row[2])
        expected_count: int = int(row[3])
        unexpected_count: int = int(row[4])
        missing_count: int = int(row[5])
        outcome: SqlTestOutcome
        if unexpected_count == 0 and missing_count == 0 and actual_count == expected_count:
            outcome = SqlTestOutcome.PASS
        else:
            outcome = SqlTestOutcome.FAIL
        step_results.append(
            StepResult(
                model_name=model_name,
                outcome=outcome,
                actual_row_count=actual_count,
                expected_row_count=expected_count,
                mismatched_row_count=unexpected_count,
                unexpected_row_count=unexpected_count,
                missing_row_count=missing_count,
            )
        )
    return step_results
