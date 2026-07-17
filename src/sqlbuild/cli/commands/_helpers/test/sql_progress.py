"""SQL unit-test progress formatting helpers."""

from __future__ import annotations

from sqlbuild.cli.progress.main._expectation_detail import format_expectation_detail
from sqlbuild.cli.progress.main._expectation_name import format_expectation_name
from sqlbuild.cli.progress.models import NestedProgressChildRow
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.presentation.main.resolve_name_column_width import resolve_name_column_width


def resolve_test_name_width(test_entries: tuple[SqlTestPlanEntry, ...]) -> int:
    """Resolve one shared width for test rows and nested expectation rows."""

    names: list[str] = []
    entry: SqlTestPlanEntry
    for entry in test_entries:
        names.append(entry.name)
        names.extend(f"expected {step.model_name}" for step in entry.chain if step.expected_cte_sql)
        names.extend(f"assertion {assertion.name}" for assertion in entry.assertions)
    return resolve_name_column_width(names=names, min_width=50)


def build_test_expectation_rows(
    result: SqlTestExecutionResult,
) -> tuple[NestedProgressChildRow, ...]:
    """Build nested expectation rows for a completed SQL unit test."""

    rows: list[NestedProgressChildRow] = []
    step_result: StepResult
    for step_result in result.step_results:
        expectation_name: str = format_expectation_name(step_result.model_name)
        status_text: str = "PASS" if step_result.outcome == SqlTestOutcome.PASS else "FAIL"
        rows.append(
            NestedProgressChildRow(
                label="expect",
                name=expectation_name,
                status_text=status_text,
                detail=format_expectation_detail(step_result),
            )
        )
    return tuple(rows)
