"""SQL unit-test progress formatting helpers."""

from __future__ import annotations

from sqlbuild.cli.commands.main.shared.models import NestedProgressChildRow
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.shared.helpers.alignment import resolve_name_column_width


def resolve_test_name_width(test_entries: tuple[SqlTestPlanEntry, ...]) -> int:
    """Resolve one shared width for test rows and nested expectation rows."""

    names: list[str] = []
    entry: SqlTestPlanEntry
    for entry in test_entries:
        names.append(entry.name)
        names.extend(f"expected {step.model_name}" for step in entry.chain if step.expected_cte_sql)
        names.extend(f"assertion {assertion.name}" for assertion in entry.assertions)
    return resolve_name_column_width(names, min_width=50)


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


def format_expectation_name(model_name: str) -> str:
    """Format a comparison result name as a user-facing expectation name."""

    if model_name.startswith("assertion "):
        return model_name
    return f"expected {model_name}"


def format_expectation_detail(step_result: StepResult) -> str:
    """Format failing row count detail for an expectation row."""

    if step_result.outcome == SqlTestOutcome.PASS:
        return ""
    if step_result.model_name.startswith("assertion "):
        row_label: str = "row" if step_result.actual_row_count == 1 else "rows"
        return f"  {step_result.actual_row_count} {row_label}"
    return f"  {step_result.mismatched_row_count} mismatched"
