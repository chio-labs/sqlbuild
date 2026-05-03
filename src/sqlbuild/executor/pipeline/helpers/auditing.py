"""Audit execution pipeline."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult


def run_audit_pipeline(
    *,
    plan: PlanOutput,
    connection_config: dict[str, object],
    adapter: BaseAdapter,
    on_audit_complete: Callable[[AuditExecutionResult], None] | None = None,
) -> tuple[AuditExecutionResult, ...]:
    """Execute all audits from a compiled plan against existing relations."""

    connection: Any = adapter.connect(connection_config)
    try:
        results: list[AuditExecutionResult] = []
        entry: AuditPlanEntry
        for entry in plan.audit_entries:
            result: AuditExecutionResult = execute_audit(
                audit=entry,
                adapter=adapter,
                connection=connection,
                model_targets=plan.model_targets,
                seed_targets=plan.seed_targets,
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
