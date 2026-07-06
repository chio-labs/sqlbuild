"""Source audit execution before dependent model chains."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.helpers.blocking import downstream_blocked_keys
from sqlbuild.executor.build.models import SourceAuditRunResult
from sqlbuild.spec.models.source import SourceEntry


def run_pending_source_audits(
    *,
    model_key: CompiledObjectKey,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    selected_keys: frozenset[CompiledObjectKey],
    source_audits_by_source: dict[str, tuple[AuditPlanEntry, ...]],
    executed_source_audits: frozenset[str],
    failed_sources: frozenset[str],
    adapter: BaseAdapter,
    connection: Any,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    fail_fast: bool,
) -> SourceAuditRunResult:
    """Execute pending source audits and return the resulting state changes."""

    any_blocked: bool = False
    executed_names: list[str] = []
    failed_names: list[str] = []
    newly_blocked: set[CompiledObjectKey] = set()
    audit_results: list[AuditExecutionResult] = []
    dep_key: CompiledObjectKey
    for dep_key in upstream_deps.get(model_key, ()):
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
                model_locations=model_locations,
                seed_locations=seed_locations,
                source_map=source_map,
                relation_overrides=None,
                run_scope_phase=AuditRunScope.FINAL,
            )
            audit_results.append(result)
            if result.outcome == AuditOutcome.ERROR:
                failed_names.append(source_name)
                newly_blocked.update(
                    downstream_blocked_keys(
                        failed_key=dep_key,
                        downstream_deps=downstream_deps,
                        selected_keys=selected_keys,
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
