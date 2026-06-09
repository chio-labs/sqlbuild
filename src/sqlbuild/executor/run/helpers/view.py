"""View materialization lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks, render_hooks
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.models import HookExecutionResult, ModelExecutionResult
from sqlbuild.executor.run.types import HookPhase
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.helpers.diagnostics_logging import diagnostics_context
from sqlbuild.shared.helpers.naming import resolve_relation_location_qualified_name
from sqlbuild.spec.models.source import SourceEntry


def execute_view_entry(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationLocation],
    seed_targets: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    run_id: str,
    query_change_tracking: bool,
    hook_functions: tuple[DiscoveredHookFunction, ...] = (),
    effective_target_name: str | None = None,
    effective_vars: Mapping[str, object] | None = None,
    providers: ProviderContainer | None = None,
) -> ModelExecutionResult:
    """Execute one view model through its full materialization lifecycle."""

    target_database: str | None = entry.destination.database
    target_schema: str | None = entry.destination.schema
    target_qualified: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=entry.destination
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []
    hook_results: list[HookExecutionResult] = []
    statement_recorder: StatementRecorder = StatementRecorder()

    try:
        statement_recorder.record_many(
            render_hooks(hooks=entry.pre_hooks, phase=HookPhase.PRE_HOOKS)
        )
        with diagnostics_context(sqlbuild_phase="pre_hook", sqlbuild_action_name="run"):
            execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.pre_hooks,
                phase=HookPhase.PRE_HOOKS,
                hook_functions=hook_functions,
                model_name=entry.name,
                destination=entry.destination,
                run_id=run_id,
                environment=effective_target_name,
                effective_vars=effective_vars,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                providers=providers,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.PRE_HOOK,
            error=str(exc),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    try:
        adapter.ensure_schema(
            connection,
            database=target_database,
            schema=target_schema,
            statement_recorder=statement_recorder,
        )
        with diagnostics_context(sqlbuild_phase="materialize", sqlbuild_action_name="create_view"):
            adapter.create_view_as(
                connection,
                target=target_qualified,
                sql=entry.resolved_sql,
                statement_recorder=statement_recorder,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.STAGING,
            error=str(exc),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    audit_error: bool = False
    audit: AuditPlanEntry
    for audit in model_audits:
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
        audit_results.append(result)
        if result.outcome == AuditOutcome.ERROR:
            audit_error = True

    if audit_error:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"final audit for '{entry.name}' failed after view creation "
                "with severity level: error"
            ),
            promoted_relation=target_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    try:
        statement_recorder.record_many(
            render_hooks(hooks=entry.post_hooks, phase=HookPhase.POST_HOOKS)
        )
        with diagnostics_context(sqlbuild_phase="post_hook", sqlbuild_action_name="run"):
            execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.post_hooks,
                phase=HookPhase.POST_HOOKS,
                hook_functions=hook_functions,
                model_name=entry.name,
                destination=entry.destination,
                run_id=run_id,
                environment=effective_target_name,
                effective_vars=effective_vars,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
                providers=providers,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.POST_HOOK,
            error=str(exc),
            promoted_relation=target_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    try_write_fingerprint(
        entry=entry,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        query_change_tracking=query_change_tracking,
        warnings=warnings,
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=target_qualified,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
        hook_results=tuple(hook_results),
    )
