"""Audit execution pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback


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
) -> tuple[AuditExecutionResult, ...]:
    """Execute all audits from a compiled plan against existing relations."""

    if on_connection_start is not None:
        on_connection_start(1)
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
            )
            results.append(result)
            if on_audit_complete is not None:
                on_audit_complete(result)
        return tuple(results)
    finally:
        adapter.close(connection)
