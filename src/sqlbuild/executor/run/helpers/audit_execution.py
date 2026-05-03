"""Audit execution within model materialization lifecycle."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.main import render_audit_sql
from sqlbuild.compiler.auditing.types import (
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.spec.models.source import SourceEntry


def execute_audit(
    *,
    audit: AuditPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    relation_overrides: dict[str, str] | None,
    run_scope_phase: AuditRunScope,
) -> AuditExecutionResult:
    """Execute one audit and produce an outcome result."""

    executed_sql: str = render_audit_sql(
        unresolved_sql=audit.unresolved_sql,
        model_targets=model_targets,
        seed_targets=seed_targets,
        source_map=source_map,
        relation_overrides=relation_overrides,
    )

    cursor: Any = adapter.execute(connection, executed_sql)
    rows: list[Any] = cursor.fetchall()
    row_count: int = len(rows)

    outcome: AuditOutcome
    if row_count == 0:
        outcome = AuditOutcome.PASS
    elif audit.severity == AuditSeverity.ERROR:
        outcome = AuditOutcome.ERROR
    else:
        outcome = AuditOutcome.WARN

    return AuditExecutionResult(
        audit_name=audit.name,
        attachment_kind=audit.attachment_kind,
        severity=audit.severity,
        outcome=outcome,
        row_count=row_count,
        executed_sql=executed_sql,
        run_scope_phase=run_scope_phase,
        attached_target_name=audit.attached_target_name,
        attached_column_name=audit.attached_column_name,
    )
