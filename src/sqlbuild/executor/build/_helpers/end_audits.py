"""End audit execution after model completion."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.main._execute import execute_audit
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.runtime.observability.classes.resource_attempt_lifecycle import (
    ResourceAttemptLifecycle,
)
from sqlbuild.spec.contracts.models import SourceEntry


def run_end_audits(
    *,
    end_audits: tuple[AuditPlanEntry, ...],
    adapter: BaseAdapter,
    connection: Any,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    run_id: str,
) -> tuple[AuditExecutionResult, ...]:
    """Execute all end audits and return results."""

    results: list[AuditExecutionResult] = []
    audit: AuditPlanEntry
    for audit in end_audits:
        with ResourceAttemptLifecycle(
            resource_id=audit_resource_id(
                audit_name=audit.name,
                attachment_kind=audit.attachment_kind,
                attached_target_name=audit.attached_target_name,
                attached_column_name=audit.attached_column_name,
            ),
            resource_kind="audit",
            resource_name=audit.name,
            run_id=run_id,
        ) as lifecycle:
            result: AuditExecutionResult = execute_audit(
                audit=audit,
                adapter=adapter,
                connection=connection,
                model_locations=model_locations,
                seed_locations=seed_locations,
                source_map=source_map,
                relation_overrides=None,
                run_scope_phase=AuditRunScope.FINAL,
            )
            if result.outcome == AuditOutcome.ERROR:
                lifecycle.failed()
        results.append(result)
    return tuple(results)
