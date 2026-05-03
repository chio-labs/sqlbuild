"""SQL unit test execution result models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.executor.testing.types import SqlTestOutcome


@dataclass(frozen=True)
class StepResult:
    """Outcome of one chain step in a SQL unit test."""

    model_name: str
    outcome: SqlTestOutcome
    actual_row_count: int = 0
    expected_row_count: int = 0
    mismatched_row_count: int = 0
    error_message: str | None = None


@dataclass(frozen=True)
class SqlTestExecutionResult:
    """Outcome of one SQL unit test execution."""

    test_name: str
    outcome: SqlTestOutcome
    step_results: tuple[StepResult, ...] = field(default_factory=tuple)
    error_message: str | None = None
