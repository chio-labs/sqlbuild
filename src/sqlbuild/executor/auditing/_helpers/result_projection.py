"""Best-effort persistence and lifecycle publication for completed audit batches."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.main.identity import build_audit_gate_identity
from sqlbuild.compiler.auditing.models import AuditIdentity, MeasurementThresholdBound
from sqlbuild.compiler.auditing.types import AuditEvaluationMode, ThresholdOperator
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.executor.audit_results.constants import AUDIT_RESULT_SCHEMA_VERSION
from sqlbuild.executor.audit_results.exceptions import AuditResultStorageError
from sqlbuild.executor.audit_results.main._write import write_audit_result_records
from sqlbuild.executor.audit_results.models import AuditResultRecord, build_audit_result_id
from sqlbuild.executor.auditing.models import AuditExecutionResult, AuditResultProjection
from sqlbuild.runtime.observability.classes.operation_lifecycle import OperationLifecycle
from sqlbuild.runtime.observability.main.current_execution_identity import (
    current_execution_identity,
)
from sqlbuild.runtime.observability.models import ExecutionIdentity
from sqlbuild.runtime.observability.types import JSONValue

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")
_LAST_AUDIT_RESULT_PROJECTION: ContextVar[AuditResultProjection | None] = ContextVar(
    "sqlbuild_last_audit_result_projection", default=None
)


def current_audit_result_projection_impl() -> AuditResultProjection | None:
    """Return the most recent audit projection report in this execution context."""

    return _LAST_AUDIT_RESULT_PROJECTION.get()


def project_audit_result_batch_impl(
    *,
    plan: PlanOutput,
    results: tuple[AuditExecutionResult, ...],
    adapter: BaseAdapter,
    connection: Any,
    storage_database: str | None = None,
    storage_schema: str | None = None,
) -> AuditResultProjection:
    """Publish and append non-reused audit facts without changing audit outcomes."""

    executed: tuple[AuditExecutionResult, ...] = tuple(
        result for result in results if not result.reused
    )
    if not executed:
        projection: AuditResultProjection = AuditResultProjection()
        _LAST_AUDIT_RESULT_PROJECTION.set(projection)
        return projection
    identity: ExecutionIdentity | None = current_execution_identity()
    if identity is None or identity.run_id is None:
        _LOGGER.warning("Audit result projection skipped because runtime identity is unavailable")
        projection = AuditResultProjection(
            attempted_count=len(executed), failed_count=len(executed)
        )
        _LAST_AUDIT_RESULT_PROJECTION.set(projection)
        return projection
    database, schema = _storage_location(
        plan=plan,
        database=storage_database,
        schema=storage_schema,
    )
    if schema is None:
        _LOGGER.warning("Audit result projection skipped because target schema is unavailable")
        projection = AuditResultProjection(
            attempted_count=len(executed), failed_count=len(executed)
        )
        _LAST_AUDIT_RESULT_PROJECTION.set(projection)
        return projection

    try:
        records: tuple[AuditResultRecord, ...] = _build_records(
            plan=plan,
            results=executed,
            identity=identity,
            storage_database=database,
            storage_schema=schema,
        )
        for record in records:
            _ = _publish_audit_completed(record)
    except Exception as error:
        _LOGGER.warning(
            "Audit result projection degraded: attempted=%d written=0 failed=%d (%s)",
            len(executed),
            len(executed),
            error,
        )
        projection = AuditResultProjection(
            attempted_count=len(executed), failed_count=len(executed)
        )
        _LAST_AUDIT_RESULT_PROJECTION.set(projection)
        return projection
    try:
        write_audit_result_records(
            connection=connection,
            execute=adapter.execute,
            database=database,
            schema=schema,
            records=records,
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
            render_create_table_sql=adapter.render_create_audit_result_table_sql,
            render_create_index_sqls=adapter.render_create_audit_result_index_sqls,
        )
    except AuditResultStorageError as error:
        _LOGGER.warning(
            "Audit result persistence degraded: attempted=%d written=0 failed=%d (%s)",
            len(records),
            len(records),
            error,
        )
        projection = AuditResultProjection(attempted_count=len(records), failed_count=len(records))
        _LAST_AUDIT_RESULT_PROJECTION.set(projection)
        return projection
    projection = AuditResultProjection(attempted_count=len(records), written_count=len(records))
    _LAST_AUDIT_RESULT_PROJECTION.set(projection)
    return projection


def _build_records(
    *,
    plan: PlanOutput,
    results: tuple[AuditExecutionResult, ...],
    identity: ExecutionIdentity,
    storage_database: str | None,
    storage_schema: str,
) -> tuple[AuditResultRecord, ...]:
    entries: list[AuditPlanEntry] = list(plan.audit_entries)
    occurrence: defaultdict[tuple[str, str], int] = defaultdict(int)
    records: list[AuditResultRecord] = []
    for result in results:
        entry: AuditPlanEntry | None = next(
            (candidate for candidate in entries if _matches(entry=candidate, result=result)),
            None,
        )
        if entry is None:
            _LOGGER.warning(
                "Audit result projection skipped unknown audit result '%s'", result.audit_name
            )
            continue
        audit_id: AuditIdentity = build_audit_gate_identity(audits=(entry,)).audits[0]
        occurrence_key: tuple[str, str] = (audit_id.binding_key, result.run_scope_phase.value)
        ordinal: int = occurrence[occurrence_key]
        occurrence[occurrence_key] += 1
        attempt_key: str = f"{result.run_scope_phase.value}:{ordinal}"
        result_id: str = build_audit_result_id(
            invocation_id=identity.invocation_id,
            run_id=identity.run_id or "",
            binding_key=audit_id.binding_key,
            execution_fingerprint=audit_id.execution_fingerprint,
            run_scope_phase=result.run_scope_phase.value,
            attempt_key=attempt_key,
        )
        target: CompiledRelationLocation | None = (
            plan.model_locations.get(result.attached_target_name)
            if result.attached_target_name is not None
            else None
        )
        thresholds: dict[str, object] | None = _render_thresholds(entry)
        evidence: list[dict[str, object]] = [dict(row) for row in result.evidence_rows]
        records.append(
            AuditResultRecord(
                result_id=result_id,
                schema_version=AUDIT_RESULT_SCHEMA_VERSION,
                occurred_at=datetime.now(UTC),
                invocation_id=identity.invocation_id,
                run_id=identity.run_id or "",
                audit_name=result.audit_name,
                binding_key=audit_id.binding_key,
                definition_fingerprint=audit_id.definition_fingerprint,
                execution_fingerprint=audit_id.execution_fingerprint,
                evaluation_mode=result.evaluation_mode.value,
                run_scope_phase=result.run_scope_phase.value,
                attachment_kind=result.attachment_kind.value,
                attached_target_kind=(
                    None
                    if result.attached_target_kind is None
                    else result.attached_target_kind.value
                ),
                attached_target_name=result.attached_target_name,
                attached_column_name=result.attached_column_name,
                target_database=(target.database if target is not None else storage_database),
                target_schema=(target.schema if target is not None else storage_schema),
                target_name=(target.name if target is not None else result.attached_target_name),
                severity=result.severity.value,
                outcome=result.outcome.value,
                execution_error=result.execution_error,
                violation_count=(
                    result.row_count
                    if result.evaluation_mode == AuditEvaluationMode.VIOLATIONS
                    else None
                ),
                measured_value=result.measured_value,
                sample_count=result.sample_count,
                sample_unit=result.sample_unit,
                minimum_samples=result.minimum_samples,
                thresholds_json=_json_or_none(thresholds),
                evidence_json=_json_or_none(evidence) if evidence else None,
                evidence_count=len(evidence),
                evidence_truncated=result.evidence_truncated,
                evidence_error=result.evidence_error,
                measurement_sql=(
                    result.executed_sql
                    if result.evaluation_mode == AuditEvaluationMode.MEASUREMENT
                    else None
                ),
                evidence_sql=result.evidence_sql,
                executed_sql=result.executed_sql,
                sql_digest=hashlib.sha256(result.executed_sql.encode("utf-8")).hexdigest(),
                metadata_json=None,
                reused=False,
            )
        )
    return tuple(records)


def _publish_audit_completed(record: AuditResultRecord) -> None:
    payload: dict[str, JSONValue] = {
        "audit_name": record.audit_name,
        "evaluation_mode": record.evaluation_mode,
        "outcome": record.outcome,
        "severity": record.severity,
        "run_scope_phase": record.run_scope_phase,
        "attachment_kind": record.attachment_kind,
        "binding_key": record.binding_key,
        "definition_fingerprint": record.definition_fingerprint,
        "execution_fingerprint": record.execution_fingerprint,
        "evidence_count": record.evidence_count or 0,
        "evidence_truncated": bool(record.evidence_truncated),
        "executed_sql": record.executed_sql,
        "sql_digest": record.sql_digest,
        "reused": False,
        "result_id": record.result_id,
    }
    optional: dict[str, JSONValue | None] = {
        "attached_target_kind": record.attached_target_kind,
        "attached_target_name": record.attached_target_name,
        "attached_column_name": record.attached_column_name,
        "target_database": record.target_database,
        "target_schema": record.target_schema,
        "target_name": record.target_name,
        "violation_count": record.violation_count,
        "measured_value": record.measured_value,
        "sample_count": record.sample_count,
        "sample_unit": record.sample_unit,
        "minimum_samples": record.minimum_samples,
        "thresholds": json.loads(record.thresholds_json) if record.thresholds_json else None,
        "evidence": json.loads(record.evidence_json) if record.evidence_json else None,
        "evidence_error": record.evidence_error,
        "measurement_sql": record.measurement_sql,
        "evidence_sql": record.evidence_sql,
        "execution_error": record.execution_error,
    }
    payload.update({key: value for key, value in optional.items() if value is not None})
    OperationLifecycle.publish_audit_completed(payload=payload)


def _render_thresholds(entry: AuditPlanEntry) -> dict[str, object] | None:
    if entry.thresholds is None:
        return None
    rendered: dict[str, object] = {}
    for name, bound in (("warn", entry.thresholds.warn), ("error", entry.thresholds.error)):
        if bound is not None:
            rendered[name] = _render_bound(bound)
    return rendered


def _render_bound(bound: MeasurementThresholdBound) -> dict[str, object]:
    if bound.operator == ThresholdOperator.OUTSIDE:
        return {"operator": bound.operator.value, "lower": bound.lower, "upper": bound.upper}
    return {"operator": bound.operator.value, "limit": bound.limit}


def _json_or_none(value: object | None) -> str | None:
    return None if value is None else json.dumps(value, sort_keys=True, separators=(",", ":"))


def _matches(*, entry: AuditPlanEntry, result: AuditExecutionResult) -> bool:
    return (
        entry.name == result.audit_name
        and entry.attachment_kind == result.attachment_kind
        and entry.attached_target_name == result.attached_target_name
        and entry.attached_column_name == result.attached_column_name
    )


def _storage_location(
    *, plan: PlanOutput, database: str | None, schema: str | None
) -> tuple[str | None, str | None]:
    if schema is not None:
        return database, schema
    location: CompiledRelationLocation
    for location in (*plan.model_locations.values(), *plan.seed_locations.values()):
        if location.schema is not None:
            return database if database is not None else location.database, location.schema
    return database, None
