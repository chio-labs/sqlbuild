"""Build audit execution entrypoint that reports raised errors as results."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing._helpers.execution import execute_audit_impl, failed_audit_result
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.spec.contracts.models import SourceEntry


def execute_audit_reporting_errors(
    *,
    audit: AuditPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    run_scope_phase: AuditRunScope,
    quality_scope: str,
) -> AuditExecutionResult:
    """Execute one build audit outside a model node, reporting a raised error as an error result."""

    try:
        return execute_audit_impl(
            audit=audit,
            adapter=adapter,
            connection=connection,
            model_locations=model_locations,
            seed_locations=seed_locations,
            source_map=source_map,
            relation_overrides=None,
            run_scope_phase=run_scope_phase,
            quality_scope=quality_scope,
        )
    except Exception as error:
        return failed_audit_result(audit=audit, error=error, run_scope_phase=run_scope_phase)
