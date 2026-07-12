"""Source audit execution before dependent model chains."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.helpers.blocking import downstream_blocked_keys
from sqlbuild.executor.build.models import SourceAuditRunResult


def run_pending_source_audits(
    *,
    model_key: CompiledObjectKey,
    plan: PlanOutput,
    source_audits_by_source: dict[str, tuple[AuditPlanEntry, ...]],
    executed_source_audits: frozenset[str],
    failed_sources: frozenset[str],
    adapter: BaseAdapter,
    connection: Any,
    fail_fast: bool,
) -> SourceAuditRunResult:
    """Execute pending source audits and return the resulting state changes."""

    any_blocked: bool = False
    executed_names: list[str] = []
    failed_names: list[str] = []
    newly_blocked: set[CompiledObjectKey] = set()
    audit_results: list[AuditExecutionResult] = []
    dep_key: CompiledObjectKey
    for dep_key in plan.upstream_deps.get(model_key, ()):
        if dep_key.resource_type != CompiledResourceType.SOURCE:
            continue
        source_name: str = dep_key.name
        if source_name in executed_source_audits:
            if source_name in failed_sources:
                any_blocked = True
            continue
        executed_names.append(source_name)
        audits: tuple[AuditPlanEntry, ...] = source_audits_by_source.get(source_name, ())
        if not audits:
            continue
        audit: AuditPlanEntry
        for audit in audits:
            result: AuditExecutionResult = execute_audit(
                audit=audit,
                adapter=adapter,
                connection=connection,
                model_locations=plan.model_locations,
                seed_locations=plan.seed_locations,
                source_map=plan.source_map,
                relation_overrides=None,
                run_scope_phase=AuditRunScope.FINAL,
            )
            audit_results.append(result)
            if result.outcome == AuditOutcome.ERROR:
                failed_names.append(source_name)
                newly_blocked.update(
                    downstream_blocked_keys(
                        failed_key=dep_key,
                        downstream_deps=plan.downstream_deps,
                        selected_keys=plan.selected_keys,
                    )
                )
                any_blocked = True
                if fail_fast:
                    return SourceAuditRunResult(
                        blocked=True,
                        executed_source_names=tuple(executed_names),
                        failed_source_names=tuple(failed_names),
                        newly_blocked_keys=tuple(newly_blocked),
                        audit_results=tuple(audit_results),
                    )
    return SourceAuditRunResult(
        blocked=any_blocked,
        executed_source_names=tuple(executed_names),
        failed_source_names=tuple(failed_names),
        newly_blocked_keys=tuple(newly_blocked),
        audit_results=tuple(audit_results),
    )
