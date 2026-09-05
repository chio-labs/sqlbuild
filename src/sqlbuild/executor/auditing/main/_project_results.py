"""Audit result projection entrypoint."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.auditing._helpers.result_projection import project_audit_result_batch_impl
from sqlbuild.executor.auditing.models import AuditExecutionResult, AuditResultProjection


def project_audit_result_batch(
    *,
    plan: PlanOutput,
    results: tuple[AuditExecutionResult, ...],
    adapter: BaseAdapter,
    connection: Any,
    storage_database: str | None = None,
    storage_schema: str | None = None,
) -> AuditResultProjection:
    """Publish and append non-reused audit facts without changing audit outcomes."""

    return project_audit_result_batch_impl(
        plan=plan,
        results=results,
        adapter=adapter,
        connection=connection,
        storage_database=storage_database,
        storage_schema=storage_schema,
    )
