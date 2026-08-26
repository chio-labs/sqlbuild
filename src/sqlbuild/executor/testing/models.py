"""SQL unit test execution result models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlbuild.compiler.discovery.models import SqlTestParameterDeclaration
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.sql_values.models import SqlValue


@dataclass(frozen=True)
class StepResult:
    """Outcome of one chain step in a SQL unit test."""

    model_name: str
    outcome: SqlTestOutcome
    actual_row_count: int = 0
    expected_row_count: int = 0
    mismatched_row_count: int = 0
    error_code: str | None = None
    error_help: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class SqlTestExecutionResult:
    """Outcome of one SQL unit test execution."""

    test_name: str
    outcome: SqlTestOutcome
    source_path: Path | None = None
    block_index: int | None = None
    parent_name: str | None = None
    case_name: str | None = None
    case_index: int | None = None
    case_fingerprint: str | None = None
    parameter_schema: tuple[SqlTestParameterDeclaration, ...] = field(default_factory=tuple)
    parameter_values: tuple[tuple[str, SqlValue], ...] = field(default_factory=tuple)
    step_results: tuple[StepResult, ...] = field(default_factory=tuple)
    error_code: str | None = None
    error_help: str | None = None
    error_message: str | None = None
