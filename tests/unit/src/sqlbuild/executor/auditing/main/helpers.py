"""Measurement audit execution test helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlbuild.compiler.auditing.models import MeasurementThresholdBound, MeasurementThresholds
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditEvaluationMode,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
    ThresholdOperator,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.main._execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult


class Cursor:
    def __init__(self, *, columns: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
        self.description: tuple[tuple[str], ...] = tuple((column,) for column in columns)
        self._rows: list[Sequence[object]] = list(rows)

    def fetchall(self) -> list[Sequence[object]]:
        return list(self._rows)

    def fetchmany(self, size: int) -> list[Sequence[object]]:
        return list(self._rows[:size])

    def __call__(self) -> Cursor:
        return self


class ErrorResponse:
    def __init__(self, error: BaseException) -> None:
        self._error: BaseException = error

    def __call__(self) -> Cursor:
        raise self._error


class Adapter:
    def __init__(self, cursors: Sequence[Cursor | ErrorResponse]) -> None:
        self._cursors: list[Cursor | ErrorResponse] = list(cursors)
        self.sql: list[str] = []

    def execute(self, *, connection: object, sql: str) -> Cursor:
        del connection
        self.sql.append(sql)
        next_result: Cursor | ErrorResponse = self._cursors.pop(0)
        return next_result()


def build_projection_entry() -> AuditPlanEntry:
    return build_entry()


def build_projection_result(*, reused: bool = False) -> AuditExecutionResult:
    return AuditExecutionResult(
        audit_name="row_rate",
        audit_definition_name="dq_column_rate",
        audit_description="Valid row percentage",
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.ERROR,
        outcome=AuditOutcome.WARN,
        row_count=0,
        executed_sql="SELECT 95 AS valid_rate",
        attached_target_name="orders",
        evaluation_mode=AuditEvaluationMode.MEASUREMENT,
        measured_value=95.0,
        thresholds=build_entry().thresholds,
        evidence_rows=({"order_id": 1},),
        evidence_truncated=True,
        evidence_sql="SELECT order_id FROM orders",
        reused=reused,
    )


def build_entry(
    *, evidence_sql: str | None = None, evidence_limit: int | None = None
) -> AuditPlanEntry:
    return AuditPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name="row_rate"),
        name="row_rate",
        definition_name="dq_column_rate",
        description="Valid row percentage",
        resolved_sql="SELECT 95 AS VALID_RATE, 10 AS TOTAL_ROWS",
        unresolved_sql="SELECT 95 AS VALID_RATE, 10 AS TOTAL_ROWS",
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.ERROR,
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=AuditRunScope.FINAL,
        evaluation_mode=AuditEvaluationMode.MEASUREMENT,
        value_column="valid_rate",
        sample_count_column="total_rows",
        sample_unit="rows",
        thresholds=MeasurementThresholds(
            warn=MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=100.0),
            error=MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=90.0),
        ),
        minimum_samples=5,
        evidence_resolved_sql=evidence_sql,
        evidence_unresolved_sql=evidence_sql,
        evidence_limit=evidence_limit,
        attached_target_name="orders",
    )


def execute_entry(*, entry: AuditPlanEntry, adapter: Adapter) -> AuditExecutionResult:
    return execute_audit(
        audit=entry,
        adapter=cast(Any, adapter),
        connection=object(),
        model_locations={},
        seed_locations={},
        source_map={},
        relation_overrides=None,
        run_scope_phase=AuditRunScope.FINAL,
    )
