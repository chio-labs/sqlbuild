"""Source audit execution before dependent model chains."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry, PlanOutput
from sqlbuild.executor.auditing.main._execute import execute_audit
from sqlbuild.executor.auditing.main.resource_id import audit_resource_id
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build._helpers.blocking import downstream_blocked_keys
from sqlbuild.executor.build.models import SourceAuditRunResult
from sqlbuild.runtime.observability.classes.resource_attempt_lifecycle import (
    ResourceAttemptLifecycle,
)


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
    run_id: str,
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
            with ResourceAttemptLifecycle(
                resource_id=audit_resource_id(
                    audit_name=audit.name,
                    attachment_kind=audit.attachment_kind,
                    attached_target_kind=audit.attached_target_kind,
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
                    model_locations=plan.model_locations,
                    seed_locations=plan.seed_locations,
                    source_map=plan.source_map,
                    relation_overrides=None,
                    run_scope_phase=AuditRunScope.FINAL,
                    quality_scope="source",
                )
                if result.outcome == AuditOutcome.ERROR:
                    lifecycle.failed()
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
