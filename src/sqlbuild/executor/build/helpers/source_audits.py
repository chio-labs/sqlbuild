"""Source audit execution before dependent model chains."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationTarget,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.helpers.blocking import block_downstream
from sqlbuild.spec.models.source import SourceEntry


def run_pending_source_audits(
    *,
    model_key: CompiledObjectKey,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    selected_keys: frozenset[CompiledObjectKey],
    source_audits_by_source: dict[str, tuple[AuditPlanEntry, ...]],
    executed_source_audits: set[str],
    failed_sources: set[str],
    blocked_keys: set[CompiledObjectKey],
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    all_source_audit_results: list[AuditExecutionResult],
    fail_fast: bool,
) -> bool:
    """Execute pending source audits for a model's direct source dependencies.

    Returns True if any source audit errored, blocking the model.
    """

    any_blocked: bool = False
    dep_key: CompiledObjectKey
    for dep_key in upstream_deps.get(model_key, ()):
        if dep_key.resource_type != CompiledResourceType.SOURCE:
            continue
        source_name: str = dep_key.name
        if source_name in executed_source_audits:
            if source_name in failed_sources:
                any_blocked = True
            continue
        executed_source_audits.add(source_name)
        audits: tuple[AuditPlanEntry, ...] = source_audits_by_source.get(source_name, ())
        if not audits:
            continue
        audit: AuditPlanEntry
        for audit in audits:
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
            all_source_audit_results.append(result)
            if result.outcome == AuditOutcome.ERROR:
                failed_sources.add(source_name)
                block_downstream(
                    failed_key=dep_key,
                    downstream_deps=downstream_deps,
                    selected_keys=selected_keys,
                    blocked_keys=blocked_keys,
                )
                any_blocked = True
                if fail_fast:
                    return True
    return any_blocked
