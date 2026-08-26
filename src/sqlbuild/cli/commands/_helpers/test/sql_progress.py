"""SQL unit-test progress formatting helpers."""

from __future__ import annotations

import json
from pathlib import Path

from sqlbuild.cli.progress.main._expectation_detail import format_expectation_detail
from sqlbuild.cli.progress.main._expectation_name import format_expectation_name
from sqlbuild.cli.progress.models import NestedProgressChildRow
from sqlbuild.compiler.discovery.models import SqlTestParameterDeclaration
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.presentation.main.resolve_name_column_width import resolve_name_column_width
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import SqlValueKind


def resolve_test_name_width(test_entries: tuple[SqlTestPlanEntry, ...]) -> int:
    """Resolve one shared width for test rows and nested expectation rows."""

    names: list[str] = []
    entry: SqlTestPlanEntry
    for entry in test_entries:
        names.append(
            format_parameterized_test_label(
                name=entry.name,
                source_path=entry.source_path,
                parameter_schema=entry.parameter_schema,
                parameter_values=entry.parameter_values,
            )
        )
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
        status_text: str = test_outcome_status(outcome=step_result.outcome)
        rows.append(
            NestedProgressChildRow(
                label="expect",
                name=expectation_name,
                status_text=status_text,
                detail=format_expectation_detail(step_result),
            )
        )
    return tuple(rows)


def format_parameterized_test_label(
    *,
    name: str,
    source_path: Path | None,
    parameter_schema: tuple[SqlTestParameterDeclaration, ...],
    parameter_values: tuple[tuple[str, SqlValue], ...],
) -> str:
    """Add source and safe typed values only for parameterized test rows."""

    if source_path is None or not parameter_values:
        return name
    schema_by_name: dict[str, SqlTestParameterDeclaration] = {
        parameter.name: parameter for parameter in parameter_schema
    }
    rendered_values: list[str] = []
    value_name: str
    value: SqlValue
    for value_name, value in parameter_values:
        declaration: SqlTestParameterDeclaration = schema_by_name[value_name]
        payload: object = str(value.value) if value.kind == SqlValueKind.DECIMAL else value.value
        rendered: str = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
        nullable: str = "?" if declaration.nullable else ""
        rendered_values.append(f"{value_name}:{declaration.value_type.value}{nullable}={rendered}")
    return f"{name} ({source_path.as_posix()}; {', '.join(rendered_values)})"


def test_outcome_status(*, outcome: SqlTestOutcome) -> str:
    """Preserve the semantic distinction between assertion failures and execution errors."""

    if outcome == SqlTestOutcome.PASS:
        return "PASS"
    if outcome == SqlTestOutcome.ERROR:
        return "ERROR"
    return "FAIL"
