"""Bounded expected-output difference sampling."""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import replace
from typing import Any, Final

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.types import TypeDialect
from sqlbuild.compiler.planner.models import ChainStep, SqlTestPlanEntry
from sqlbuild.diagnostics.classes.diagnostic_record_redactor import DiagnosticRecordRedactor
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.executor.testing._helpers.comparison_sql import format_sql, lift_step_ctes
from sqlbuild.executor.testing.models import SqlTestDifferenceSample, StepResult
from sqlbuild.executor.testing.types import SqlTestDifferenceDirection, SqlTestOutcome

_ROW_LIMIT: Final[int] = 3
_COLUMN_LIMIT: Final[int] = 12
_VALUE_LIMIT: Final[int] = 120
_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


def add_difference_samples(
    *,
    step_results: list[StepResult],
    test_entry: SqlTestPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
) -> list[StepResult]:
    """Attach bounded, redacted samples to failed expected-output steps."""

    sampled_results: list[StepResult] = []
    expected_steps: tuple[ChainStep, ...] = tuple(
        step for step in test_entry.chain if step.expected_cte_sql is not None
    )
    for step_index, step_result in enumerate(step_results):
        if step_index >= len(expected_steps) or step_result.outcome != SqlTestOutcome.FAIL:
            sampled_results.append(step_result)
            continue
        step: ChainStep = expected_steps[step_index]
        unexpected_samples: tuple[SqlTestDifferenceSample, ...] = ()
        missing_samples: tuple[SqlTestDifferenceSample, ...] = ()
        if step_result.unexpected_row_count is not None and step_result.unexpected_row_count > 0:
            unexpected_samples = _best_effort_difference_samples(
                test_entry=test_entry,
                step=step,
                direction=SqlTestDifferenceDirection.UNEXPECTED,
                adapter=adapter,
                connection=connection,
            )
        if step_result.missing_row_count is not None and step_result.missing_row_count > 0:
            missing_samples = _best_effort_difference_samples(
                test_entry=test_entry,
                step=step,
                direction=SqlTestDifferenceDirection.MISSING,
                adapter=adapter,
                connection=connection,
            )
        sampled_results.append(
            replace(
                step_result,
                unexpected_samples=unexpected_samples,
                missing_samples=missing_samples,
            )
        )
    return sampled_results


def build_sql_test_difference_sample_sql(
    *,
    test_entry: SqlTestPlanEntry,
    step: ChainStep,
    direction: SqlTestDifferenceDirection,
    sample_limit: int,
    set_difference_operator: str = "EXCEPT",
    sql_analysis_dialect: str | None = None,
) -> str:
    """Build a bounded query for one direction of an expected-output difference."""

    if step.expected_cte_sql is None:
        return ""
    lifted_ctes: OrderedDict[str, str] = OrderedDict()
    actual_sql, lifted_ctes = lift_step_ctes(
        sql=step.resolved_sql,
        lifted_ctes=lifted_ctes,
        sql_analysis_enabled=test_entry.sql_analysis_enabled,
    )
    expected_sql, lifted_ctes = lift_step_ctes(
        sql=step.expected_cte_sql,
        lifted_ctes=lifted_ctes,
        sql_analysis_enabled=test_entry.sql_analysis_enabled,
    )
    cte_parts: list[str] = [f"{name} AS ({sql})" for name, sql in lifted_ctes.items()]
    cte_parts.extend((f"__actual AS ({actual_sql})", f"__expected AS ({expected_sql})"))
    is_unexpected: bool = direction == SqlTestDifferenceDirection.UNEXPECTED
    left: str = "__actual" if is_unexpected else "__expected"
    right: str = "__expected" if is_unexpected else "__actual"
    bounded_select: str = (
        f"SELECT TOP {sample_limit} *" if sql_analysis_dialect == TypeDialect.TSQL else "SELECT *"
    )
    limit_clause: str = "" if sql_analysis_dialect == TypeDialect.TSQL else f" LIMIT {sample_limit}"
    sql: str = (
        f"WITH {', '.join(cte_parts)} {bounded_select} FROM ("
        f"SELECT * FROM {left} {set_difference_operator} SELECT * FROM {right}"
        f") AS __sqlbuild_difference{limit_clause}"
    )
    return format_sql(
        sql=sql,
        sql_analysis_dialect=sql_analysis_dialect,
        sql_analysis_enabled=test_entry.sql_analysis_enabled,
    )


def _fetch_difference_samples(
    *,
    test_entry: SqlTestPlanEntry,
    step: ChainStep,
    direction: SqlTestDifferenceDirection,
    adapter: BaseAdapter,
    connection: Any,
) -> tuple[SqlTestDifferenceSample, ...]:
    sql: str = build_sql_test_difference_sample_sql(
        test_entry=test_entry,
        step=step,
        direction=direction,
        sample_limit=_ROW_LIMIT,
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )
    cursor: Any = adapter.execute(connection=connection, sql=sql)
    description: Any | None = getattr(cursor, "description", None)
    if description is None:
        return ()
    column_names: tuple[str, ...] = tuple(str(column[0]) for column in description)
    if not column_names:
        return ()
    rows: list[Any] = cursor.fetchall()
    samples: list[SqlTestDifferenceSample] = []
    for row in rows[:_ROW_LIMIT]:
        values: list[tuple[str, str]] = [
            (column_name, _safe_sample_value(name=column_name, value=value))
            for column_name, value in list(zip(column_names, row, strict=False))[:_COLUMN_LIMIT]
        ]
        omitted_columns: int = max(0, len(column_names) - _COLUMN_LIMIT)
        if omitted_columns:
            values.append(("...", f"{omitted_columns} columns omitted"))
        samples.append(SqlTestDifferenceSample(values=tuple(values)))
    return tuple(samples)


def _best_effort_difference_samples(
    *,
    test_entry: SqlTestPlanEntry,
    step: ChainStep,
    direction: SqlTestDifferenceDirection,
    adapter: BaseAdapter,
    connection: Any,
) -> tuple[SqlTestDifferenceSample, ...]:
    """Return samples when available without replacing a known comparison failure."""

    try:
        return _fetch_difference_samples(
            test_entry=test_entry,
            step=step,
            direction=direction,
            adapter=adapter,
            connection=connection,
        )
    except Exception as error:
        log_debug_event(
            logger=_LOGGER,
            message="SQL test difference sampling failed; preserving comparison result",
            test_name=test_entry.name,
            model_name=step.model_name,
            direction=direction.value,
            sqlbuild_error=DiagnosticRecordRedactor.text(str(error)),
        )
        return ()


def _safe_sample_value(*, name: str, value: object) -> str:
    safe_value: object = DiagnosticRecordRedactor.value(name=name, value=value)
    rendered: str = "NULL" if safe_value is None else " ".join(str(safe_value).split())
    if len(rendered) <= _VALUE_LIMIT:
        return rendered
    return f"{rendered[: _VALUE_LIMIT - 3]}..."
