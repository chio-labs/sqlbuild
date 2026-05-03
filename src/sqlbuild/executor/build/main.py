"""Build execution orchestration over a planned execution schedule."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    SeedPlanEntry,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.build.constants import INCREMENTAL_ACTIONS
from sqlbuild.executor.build.helpers.blocking import block_downstream
from sqlbuild.executor.build.helpers.end_audits import run_end_audits
from sqlbuild.executor.build.helpers.indexes import build_execution_indexes
from sqlbuild.executor.build.helpers.seeds import execute_seed
from sqlbuild.executor.build.helpers.source_audits import run_pending_source_audits
from sqlbuild.executor.build.models import (
    BuildExecutionResult,
    BuildIndexes,
    SeedExecutionResult,
)
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.run.main import execute_incremental_entry, execute_table_entry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus, TablePromotionMode


def execute_build_plan(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    promotion_mode: TablePromotionMode,
    run_id: str,
    fingerprint_schema: str | None = None,
    run_audits: bool = True,
    run_tests: bool = True,
    fail_fast: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> BuildExecutionResult:
    """Execute a full build plan over the planned execution schedule."""

    indexes: BuildIndexes = build_execution_indexes(plan)
    blocked_keys: set[CompiledObjectKey] = set()
    executed_source_audits: set[str] = set()
    failed_sources: set[str] = set()

    model_results: list[ModelExecutionResult] = []
    seed_results: list[SeedExecutionResult] = []
    source_audit_results: list[AuditExecutionResult] = []

    key: CompiledObjectKey
    for key in plan.execution_order:
        if key in blocked_keys:
            _record_skipped(
                key=key,
                indexes=indexes,
                model_results=model_results,
                seed_results=seed_results,
            )
            continue

        if key.resource_type == CompiledResourceType.SEED:
            seed_entry: SeedPlanEntry | None = indexes.seed_entries_by_key.get(key)
            if seed_entry is None:
                continue
            if on_progress is not None:
                on_progress(f"seed: {seed_entry.name}")
            seed_result: SeedExecutionResult = execute_seed(
                seed_entry=seed_entry, adapter=adapter, connection=connection
            )
            seed_results.append(seed_result)
            if seed_result.status == ExecutionStatus.FAILED:
                block_downstream(
                    failed_key=key,
                    downstream_deps=plan.downstream_deps,
                    selected_keys=plan.selected_keys,
                    blocked_keys=blocked_keys,
                )
                if fail_fast:
                    break
            continue

        if key.resource_type == CompiledResourceType.MODEL:
            model_entry: ModelPlanEntry | None = indexes.model_entries_by_key.get(key)
            if model_entry is None:
                continue

            if run_audits:
                source_blocked: bool = run_pending_source_audits(
                    model_key=key,
                    upstream_deps=plan.upstream_deps,
                    downstream_deps=plan.downstream_deps,
                    selected_keys=plan.selected_keys,
                    source_audits_by_source=indexes.source_audits_by_source,
                    executed_source_audits=executed_source_audits,
                    failed_sources=failed_sources,
                    blocked_keys=blocked_keys,
                    adapter=adapter,
                    connection=connection,
                    model_targets=plan.model_targets,
                    seed_targets=plan.seed_targets,
                    source_map=plan.source_map,
                    all_source_audit_results=source_audit_results,
                    fail_fast=fail_fast,
                )
                if source_blocked:
                    blocked_keys.add(key)
                    model_results.append(
                        ModelExecutionResult(
                            model_name=model_entry.name,
                            status=ExecutionStatus.SKIPPED,
                        )
                    )
                    if fail_fast:
                        break
                    continue

            if on_progress is not None:
                on_progress(f"model: {model_entry.name}")

            model_audits: tuple[AuditPlanEntry, ...] = (
                indexes.model_audits_by_model.get(model_entry.name, ()) if run_audits else ()
            )

            model_result: ModelExecutionResult
            if model_entry.action in INCREMENTAL_ACTIONS:
                model_result = execute_incremental_entry(
                    entry=model_entry,
                    adapter=adapter,
                    connection=connection,
                    model_targets=plan.model_targets,
                    seed_targets=plan.seed_targets,
                    source_map=plan.source_map,
                    model_audits=model_audits,
                    declared_columns=model_entry.declared_columns,
                    run_id=run_id,
                    fingerprint_schema=fingerprint_schema,
                )
            else:
                model_result = execute_table_entry(
                    entry=model_entry,
                    adapter=adapter,
                    connection=connection,
                    model_targets=plan.model_targets,
                    seed_targets=plan.seed_targets,
                    source_map=plan.source_map,
                    model_audits=model_audits,
                    declared_columns=model_entry.declared_columns,
                    promotion_mode=promotion_mode,
                    run_id=run_id,
                    fingerprint_schema=fingerprint_schema,
                )
            model_results.append(model_result)

            if model_result.status == ExecutionStatus.FAILED:
                block_downstream(
                    failed_key=key,
                    downstream_deps=plan.downstream_deps,
                    selected_keys=plan.selected_keys,
                    blocked_keys=blocked_keys,
                )
                if fail_fast:
                    break
            continue

    end_audit_results: tuple[AuditExecutionResult, ...] = ()
    if run_audits and indexes.end_audits:
        end_audit_results = run_end_audits(
            end_audits=indexes.end_audits,
            adapter=adapter,
            connection=connection,
            model_targets=plan.model_targets,
            seed_targets=plan.seed_targets,
            source_map=plan.source_map,
        )

    return _aggregate_build_result(
        model_results=model_results,
        seed_results=seed_results,
        source_audit_results=source_audit_results,
        end_audit_results=end_audit_results,
    )


def _record_skipped(
    *,
    key: CompiledObjectKey,
    indexes: BuildIndexes,
    model_results: list[ModelExecutionResult],
    seed_results: list[SeedExecutionResult],
) -> None:
    """Record a SKIPPED result for a blocked key."""

    if key.resource_type == CompiledResourceType.MODEL:
        model_entry: ModelPlanEntry | None = indexes.model_entries_by_key.get(key)
        if model_entry is not None:
            model_results.append(
                ModelExecutionResult(
                    model_name=model_entry.name,
                    status=ExecutionStatus.SKIPPED,
                )
            )
    elif key.resource_type == CompiledResourceType.SEED:
        seed_entry: SeedPlanEntry | None = indexes.seed_entries_by_key.get(key)
        if seed_entry is not None:
            seed_results.append(
                SeedExecutionResult(
                    seed_name=seed_entry.name,
                    status=ExecutionStatus.SKIPPED,
                )
            )


def _aggregate_build_result(
    *,
    model_results: list[ModelExecutionResult],
    seed_results: list[SeedExecutionResult],
    source_audit_results: list[AuditExecutionResult],
    end_audit_results: tuple[AuditExecutionResult, ...],
) -> BuildExecutionResult:
    """Compute aggregate counts and overall build status."""

    success_count: int = 0
    failure_count: int = 0
    skipped_count: int = 0
    warning_count: int = 0

    model_result: ModelExecutionResult
    for model_result in model_results:
        if model_result.status == ExecutionStatus.SUCCESS:
            success_count += 1
        elif model_result.status == ExecutionStatus.FAILED:
            failure_count += 1
        elif model_result.status == ExecutionStatus.SKIPPED:
            skipped_count += 1
        warning_count += len(model_result.warning_messages)
        audit_result: AuditExecutionResult
        for audit_result in model_result.audit_results:
            if audit_result.outcome == AuditOutcome.WARN:
                warning_count += 1

    seed_result: SeedExecutionResult
    for seed_result in seed_results:
        if seed_result.status == ExecutionStatus.SUCCESS:
            success_count += 1
        elif seed_result.status == ExecutionStatus.FAILED:
            failure_count += 1
        elif seed_result.status == ExecutionStatus.SKIPPED:
            skipped_count += 1

    any_end_error: bool = False
    end_result: AuditExecutionResult
    for end_result in end_audit_results:
        if end_result.outcome == AuditOutcome.ERROR:
            any_end_error = True
        elif end_result.outcome == AuditOutcome.WARN:
            warning_count += 1

    source_result: AuditExecutionResult
    for source_result in source_audit_results:
        if source_result.outcome == AuditOutcome.ERROR:
            failure_count += 1
        elif source_result.outcome == AuditOutcome.WARN:
            warning_count += 1

    overall_failed: bool = failure_count > 0 or any_end_error
    status: BuildStatus = BuildStatus.FAILED if overall_failed else BuildStatus.SUCCESS

    return BuildExecutionResult(
        status=status,
        model_results=tuple(model_results),
        seed_results=tuple(seed_results),
        source_audit_results=tuple(source_audit_results),
        end_audit_results=end_audit_results,
        success_count=success_count,
        failure_count=failure_count,
        skipped_count=skipped_count,
        warning_count=warning_count,
    )
