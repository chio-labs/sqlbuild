"""Final model audit execution against the staged relation."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.reuse.audit import (
    audit_plan_binding_key,
    reused_final_audit_results_by_binding_key,
)
from sqlbuild.executor.run.models import FinalAuditRun
from sqlbuild.spec.models.source import SourceEntry


def run_final_model_audits(
    *,
    relation_overrides: dict[str, str] | None,
    model_audits: tuple[AuditPlanEntry, ...],
    reuse_origin_fingerprint: Fingerprint | None,
    adapter: BaseAdapter,
    connection: Any,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
) -> FinalAuditRun:
    """Run final audits, reusing proven results when possible."""

    reused_audit_results_by_binding_key: dict[str, AuditExecutionResult] = (
        reused_final_audit_results_by_binding_key(
            metadata_json=reuse_origin_fingerprint.metadata_json,
            model_audits=model_audits,
        )
        if reuse_origin_fingerprint is not None
        else {}
    )
    results: list[AuditExecutionResult] = []
    has_error: bool = False
    audit: AuditPlanEntry
    for audit in model_audits:
        reused_result: AuditExecutionResult | None = reused_audit_results_by_binding_key.get(
            audit_plan_binding_key(audit)
        )
        if reused_result is not None:
            results.append(reused_result)
            continue
        result: AuditExecutionResult = execute_audit(
            audit=audit,
            adapter=adapter,
            connection=connection,
            model_locations=model_locations,
            seed_locations=seed_locations,
            source_map=source_map,
            relation_overrides=relation_overrides,
            run_scope_phase=AuditRunScope.FINAL,
        )
        results.append(result)
        if result.outcome == AuditOutcome.ERROR:
            has_error = True
    return FinalAuditRun(results=tuple(results), has_error=has_error)
