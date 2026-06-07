"""Custom materialization execution lifecycle."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo, StatementRecorder
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry, SchemaFinding
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.custom.models import MaterializationContext, MaterializationResult
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.models import HookExecutionResult, ModelExecutionResult
from sqlbuild.executor.run.types import HookPhase
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.provider.main.runtime import (
    ProviderContainer,
    _empty_provider_container,
    invoke_with_providers,
)
from sqlbuild.shared.helpers.diagnostics_logging import diagnostics_context
from sqlbuild.shared.helpers.naming import resolve_destination_qualified_name
from sqlbuild.spec.models.source import SourceEntry


def execute_custom_entry(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationDestination],
    seed_targets: dict[str, CompiledRelationDestination],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    declared_columns: tuple[ColumnInfo, ...],
    materialize_fn: Callable[[MaterializationContext], MaterializationResult],
    run_id: str,
    query_change_tracking: bool,
    target: str,
    effective_vars: dict[str, object],
    existing_relation: RelationInfo | None,
    on_progress: Callable[[str], None] | None = None,
    hook_functions: tuple[DiscoveredHookFunction, ...] = (),
    effective_target_name: str | None = None,
    providers: ProviderContainer | None = None,
) -> ModelExecutionResult:
    """Execute one model through the custom materialization lifecycle."""

    destination_database: str | None = entry.destination.database
    destination_schema: str | None = entry.destination.schema
    destination_name: str = entry.destination.name
    destination_qualified: str = resolve_destination_qualified_name(
        adapter=adapter, target=entry.destination
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []
    hook_results: list[HookExecutionResult] = []
    statement_recorder: StatementRecorder = StatementRecorder()

    adapter.ensure_schema(
        connection,
        database=destination_database,
        schema=destination_schema,
        statement_recorder=statement_recorder,
    )

    try:
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

    config_dict: dict[str, Any] = dict(entry.custom_config)
    placeholders_dict: dict[str, str] = dict(entry.custom_placeholders)
    context_providers: ProviderContainer = providers or _empty_provider_container()

    run_audits_fn: Callable[[str], tuple[AuditExecutionResult, ...]] = _build_run_audits(
        model_audits=model_audits,
        adapter=adapter,
        connection=connection,
        model_targets=model_targets,
        seed_targets=seed_targets,
        source_map=source_map,
        model_name=entry.name,
    )

    is_first_run: bool = existing_relation is None
    is_full_refresh: bool = entry.reason == PlanReason.FULL_REFRESH
    query_changed: bool = entry.reason == PlanReason.QUERY_CHANGED
    schema_findings: tuple[SchemaFinding, ...] = entry.schema_findings

    ctx: MaterializationContext = MaterializationContext(
        adapter=adapter,
        connection=connection,
        destination=destination_qualified,
        destination_database=destination_database,
        destination_schema=destination_schema,
        destination_name=destination_name,
        sql=entry.resolved_sql,
        config=config_dict,
        placeholders=placeholders_dict,
        existing_relation=existing_relation,
        run_id=run_id,
        build_target=target,
        vars=effective_vars,
        unique_key=entry.unique_key,
        declared_columns=declared_columns,
        is_first_run=is_first_run,
        is_full_refresh=is_full_refresh,
        query_changed=query_changed,
        schema_findings=schema_findings,
        run_audits=run_audits_fn,
        on_progress=on_progress,
        logger=logging.getLogger(f"sqlbuild.materialization.{entry.name}"),
        statement_recorder=statement_recorder,
        providers=context_providers,
    )

    try:
        with diagnostics_context(sqlbuild_phase="materialize", sqlbuild_action_name="custom"):
            result: object = invoke_with_providers(
                function=materialize_fn,
                context=ctx,
                providers=providers,
            )
            materialization_result: MaterializationResult = cast(MaterializationResult, result)
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
            error=str(exc),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    if materialization_result.failed:
        user_audit_results: list[AuditExecutionResult] = (
            list(materialization_result.audit_results)
            if materialization_result.audit_results is not None
            else []
        )
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
            error=materialization_result.error or "custom materialization reported failure",
            warnings=warnings,
            audit_results=user_audit_results,
            statement_recorder=statement_recorder,
        )

    if materialization_result.audit_results is not None:
        audit_results.extend(materialization_result.audit_results)
    else:
        audit_error: bool = False
        audit: AuditPlanEntry
        for audit in model_audits:
            audit_result: AuditExecutionResult = execute_audit(
                audit=audit,
                adapter=adapter,
                connection=connection,
                model_targets=model_targets,
                seed_targets=seed_targets,
                source_map=source_map,
                relation_overrides=None,
                run_scope_phase=AuditRunScope.FINAL,
            )
            audit_results.append(audit_result)
            if audit_result.outcome == AuditOutcome.ERROR:
                audit_error = True

        if audit_error:
            _cleanup_relations(
                adapter=adapter,
                connection=connection,
                relations=materialization_result.cleanup_relations,
                keep=True,
                statement_recorder=statement_recorder,
            )
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.AUDIT,
                error=(
                    f"final audit for '{entry.name}' failed after materialization "
                    "with severity level: error"
                ),
                promoted_relation=materialization_result.relation,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )

    try:
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
            )
    except Exception as exc:
        _cleanup_relations(
            adapter=adapter,
            connection=connection,
            relations=materialization_result.cleanup_relations,
            keep=True,
            statement_recorder=statement_recorder,
        )
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.POST_HOOK,
            error=str(exc),
            promoted_relation=materialization_result.relation,
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

    _cleanup_relations(
        adapter=adapter,
        connection=connection,
        relations=materialization_result.cleanup_relations,
        keep=False,
        statement_recorder=statement_recorder,
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=materialization_result.relation,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
        hook_results=tuple(hook_results),
    )


def _build_run_audits(
    *,
    model_audits: tuple[AuditPlanEntry, ...],
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationDestination],
    seed_targets: dict[str, CompiledRelationDestination],
    source_map: dict[str, SourceEntry],
    model_name: str,
) -> Callable[[str], tuple[AuditExecutionResult, ...]]:
    """Build the run_audits callable for the materialization context."""

    def run_audits(against: str) -> tuple[AuditExecutionResult, ...]:
        overrides: dict[str, str] = {model_name: against}
        results: list[AuditExecutionResult] = []
        audit: AuditPlanEntry
        for audit in model_audits:
            result: AuditExecutionResult = execute_audit(
                audit=audit,
                adapter=adapter,
                connection=connection,
                model_targets=model_targets,
                seed_targets=seed_targets,
                source_map=source_map,
                relation_overrides=overrides,
                run_scope_phase=AuditRunScope.FINAL,
            )
            results.append(result)
        return tuple(results)

    return run_audits


def _cleanup_relations(
    *,
    adapter: BaseAdapter,
    connection: Any,
    relations: tuple[str, ...],
    keep: bool,
    statement_recorder: StatementRecorder,
) -> None:
    """Drop cleanup relations on success, keep on failure."""

    if keep or not relations:
        return

    relation: str
    for relation in relations:
        try:
            adapter.drop(
                connection,
                target=relation,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        except Exception:
            pass
