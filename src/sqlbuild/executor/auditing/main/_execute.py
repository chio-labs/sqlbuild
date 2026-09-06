"""Audit execution entrypoint."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing._helpers.execution import execute_audit_impl
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
    quality_scope: str | None = None,
) -> AuditExecutionResult:
    """Execute and evaluate one audit, returning quality failure as result data."""

    return execute_audit_impl(
        audit=audit,
        adapter=adapter,
        connection=connection,
        model_locations=model_locations,
        seed_locations=seed_locations,
        source_map=source_map,
        relation_overrides=relation_overrides,
        run_scope_phase=run_scope_phase,
        quality_scope=quality_scope,
    )
