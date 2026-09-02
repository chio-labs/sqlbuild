"""Audit execution pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.executor.auditing.main._execute import execute_audit
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback
from sqlbuild.runtime.observability.classes.resource_attempt_lifecycle import (
    ResourceAttemptLifecycle,
)


def run_audit_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: ConnectionElapsedCallback | None = None,
    on_connection_error: ConnectionElapsedCallback | None = None,
    on_audit_start: Callable[[AuditPlanEntry], None] | None = None,
    on_audit_complete: Callable[[AuditExecutionResult], None] | None = None,
    run_id: str | None = None,
) -> tuple[AuditExecutionResult, ...]:
    """Execute all audits from a compiled plan against existing relations."""

    if on_connection_start is not None:
        on_connection_start(1)
    canonical_run_id: str = run_id or uuid4().hex
    import time

    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, elapsed_seconds=time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, elapsed_seconds=time.monotonic() - start)
    try:
        results: list[AuditExecutionResult] = []
        entry: AuditPlanEntry
        for entry in plan.audit_entries:
            with ResourceAttemptLifecycle(
                resource_id=audit_resource_id(
                    audit_name=entry.name,
                    attachment_kind=entry.attachment_kind,
                    attached_target_name=entry.attached_target_name,
                    attached_column_name=entry.attached_column_name,
                ),
                resource_kind="audit",
                resource_name=entry.name,
                run_id=canonical_run_id,
            ) as lifecycle:
                if on_audit_start is not None:
                    on_audit_start(entry)
                result: AuditExecutionResult = execute_audit(
                    audit=entry,
                    adapter=adapter,
                    connection=connection,
                    model_locations=plan.model_locations,
                    seed_locations=plan.seed_locations,
                    source_map=plan.source_map,
                    relation_overrides=None,
                    run_scope_phase=AuditRunScope.FINAL,
                    quality_scope="standalone",
                )
                if result.outcome == AuditOutcome.ERROR:
                    lifecycle.failed()
            results.append(result)
            if on_audit_complete is not None:
                on_audit_complete(result)
        return tuple(results)
    finally:
        adapter.close(connection)
