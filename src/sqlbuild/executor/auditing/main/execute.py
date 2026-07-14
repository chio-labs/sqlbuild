"""Audit execution within build and model lifecycle."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.main.render import render_audit_sql
from sqlbuild.compiler.auditing.types import (
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.compiler.references.main.assert_no_unresolved_sql_markers import (
    assert_no_unresolved_sql_markers,
)
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.spec.contracts.models import SourceEntry


def execute_audit(
    *,
    audit: AuditPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    relation_overrides: dict[str, str] | None,
    run_scope_phase: AuditRunScope,
) -> AuditExecutionResult:
    """Execute one audit and produce an outcome result."""

    executed_sql: str = (
        audit.resolved_sql
        if relation_overrides is None
        else render_audit_sql(
            unresolved_sql=audit.unresolved_sql,
            model_locations=model_locations,
            seed_locations=seed_locations,
            source_map=source_map,
            adapter=adapter,
            relation_overrides=relation_overrides,
        )
    )
    _ = assert_no_unresolved_sql_markers(
        sql=executed_sql,
        context=f"audit '{audit.name}' executable SQL",
    )

    with diagnostics_context(
        sqlbuild_phase="audit",
        sqlbuild_audit_name=audit.name,
        sqlbuild_column_name=audit.attached_column_name,
    ):
        cursor: Any = adapter.execute(connection=connection, sql=executed_sql)
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
