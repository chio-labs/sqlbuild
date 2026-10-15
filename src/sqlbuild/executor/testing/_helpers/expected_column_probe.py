"""Explain failed comparisons caused by expected columns the model does not output."""

from __future__ import annotations

import logging
from typing import Any

from sqlbuild._native import (
    SqlTestPlanEntry,
    describe_missing_expected_columns,
    render_sql_test_comparison_sql,
)
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.diagnostics.classes.diagnostic_record_redactor import DiagnosticRecordRedactor
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


def missing_expected_columns_message(
    *, test_entry: SqlTestPlanEntry, adapter: BaseAdapter, connection: Any
) -> str | None:
    """Probe actual step columns after a failed comparison and describe missing ones."""

    for step_index, step in enumerate(test_entry.chain):
        if step.expected_columns is None or step.expected_cte_sql is None:
            continue
        available_columns: frozenset[str] | None = _probe_actual_columns(
            test_entry=test_entry, step_index=step_index, adapter=adapter, connection=connection
        )
        if available_columns is None:
            continue
        message: str | None = describe_missing_expected_columns(
            model_name=step.model_name,
            expected_columns=step.expected_columns,
            available_columns=available_columns,
        )
        if message is not None:
            return f"SQL test '{test_entry.name}': {message}"
    return None


def _probe_actual_columns(
    *, test_entry: SqlTestPlanEntry, step_index: int, adapter: BaseAdapter, connection: Any
) -> frozenset[str] | None:
    (sql,) = render_sql_test_comparison_sql(
        (test_entry,),
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
        probe_step_index=step_index,
    )
    if not sql:
        return None
    try:
        cursor: Any = adapter.execute(
            connection=connection,
            sql=sql,
        )
        description: Any | None = getattr(cursor, "description", None)
    except Exception as error:
        log_debug_event(
            logger=_LOGGER,
            message="SQL test actual column probe failed; preserving comparison error",
            test_name=test_entry.name,
            sqlbuild_error=DiagnosticRecordRedactor.text(str(error)),
        )
        return None
    if not description:
        return None
    return frozenset(str(column[0]).casefold() for column in description)
