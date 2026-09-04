"""Neutral SQL expectation detail formatting."""

from __future__ import annotations

from sqlbuild.executor.testing.models import SqlTestDifferenceSample, StepResult
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
    if (
        step_result.unexpected_row_count is None
        and step_result.missing_row_count is None
        and not step_result.unexpected_samples
        and not step_result.missing_samples
    ):
        return f"  {step_result.mismatched_row_count} mismatched"
    parts: list[str] = [
        f"unexpected={step_result.unexpected_row_count}",
        f"missing={step_result.missing_row_count}",
    ]
    if step_result.actual_row_count != step_result.expected_row_count:
        parts.append(
            f"row counts actual={step_result.actual_row_count} "
            f"expected={step_result.expected_row_count}"
        )
    parts.extend(_format_samples(label="unexpected sample", samples=step_result.unexpected_samples))
    parts.extend(_format_samples(label="missing sample", samples=step_result.missing_samples))
    return f"  {'; '.join(parts)}"


def _format_samples(*, label: str, samples: tuple[SqlTestDifferenceSample, ...]) -> tuple[str, ...]:
    """Format already-safe representative rows for terminal output."""

    lines: list[str] = []
    for index, sample in enumerate(samples, start=1):
        rendered_values: str = ", ".join(f"{name}={value}" for name, value in sample.values)
        lines.append(f"{label} {index}: {rendered_values}")
    return tuple(lines)
