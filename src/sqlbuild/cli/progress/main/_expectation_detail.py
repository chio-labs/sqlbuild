"""Neutral SQL expectation detail formatting."""

from __future__ import annotations

from sqlbuild.executor.testing.models import StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome


def format_expectation_detail(step_result: StepResult) -> str:
    """Format failing row count detail for an expectation row."""

    if step_result.outcome == SqlTestOutcome.PASS:
        return ""
    if step_result.outcome == SqlTestOutcome.ERROR:
        return ""
    if step_result.model_name.startswith("assertion "):
        row_label: str = "row" if step_result.actual_row_count == 1 else "rows"
        return f"  {step_result.actual_row_count} {row_label}"
    return f"  {step_result.mismatched_row_count} mismatched"
