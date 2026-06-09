"""End audit execution after model completion."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.spec.models.source import SourceEntry


def run_end_audits(
    *,
    end_audits: tuple[AuditPlanEntry, ...],
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationLocation],
    seed_targets: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
) -> tuple[AuditExecutionResult, ...]:
    """Execute all end audits and return results."""

    results: list[AuditExecutionResult] = []
    audit: AuditPlanEntry
    for audit in end_audits:
        result: AuditExecutionResult = execute_audit(
            audit=audit,
            adapter=adapter,
            connection=connection,
            model_targets=model_targets,
            seed_targets=seed_targets,
            source_map=source_map,
            relation_overrides=None,
            run_scope_phase=AuditRunScope.FINAL,
        )
        results.append(result)
    return tuple(results)
