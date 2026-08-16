"""Custom materialization execution lifecycle."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.executor.auditing.main._execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.custom.models import (
    MaterializationContext,
    MaterializationResult,
    PrepareVersionContext,
)
from sqlbuild.executor.run._helpers.execution.final_audits import run_final_scope_audits
from sqlbuild.executor.run._helpers.execution.hooks import execute_hooks
from sqlbuild.executor.run._helpers.execution.results import (
    build_failed_result,
    build_skipped_result,
)
from sqlbuild.executor.run._helpers.reuse.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.models import (
    CustomLifecyclePhaseOutcome,
    CustomLifecycleState,
    CustomMaterializationPhaseOutcome,
    CustomMaterializationSetup,
    FinalAuditRun,
    HookRunContext,
    ModelExecutionResult,
    ModelMaterializationContext,
)
from sqlbuild.executor.run.types import ExecutionPhase, HookPhase
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.provider.main.runtime import _empty_provider_container, invoke_with_providers
from sqlbuild.spec.contracts.models import SourceEntry


def execute_custom_entry(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
    materialize_fn: Callable[[MaterializationContext], MaterializationResult],
    target: str,
    effective_vars: dict[str, object],
    existing_relation: RelationInfo | None,
    prepare_version_fn: Callable[[PrepareVersionContext], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> ModelExecutionResult:
    """Execute one model through the custom materialization lifecycle."""

    entry: ModelPlanEntry = context.entry
    adapter: BaseAdapter = context.adapter
    connection: Any = context.connection
    destination_database: str | None = entry.destination.database
    destination_schema: str | None = entry.destination.schema
    destination_qualified: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=entry.destination
    )
    state: CustomLifecycleState = CustomLifecycleState(
        warnings=[],
        audit_results=[],
        hook_results=[],
        statement_recorder=StatementRecorder(),
    )

    adapter.ensure_schema(
        connection=connection,
        database=destination_database,
        schema=destination_schema,
        statement_recorder=state.statement_recorder,
    )
    pre_hook_exit: ModelExecutionResult | None = _run_custom_pre_hooks(
        context=context,
        effective_vars=effective_vars,
        state=state,
    )
    if pre_hook_exit is not None:
        return pre_hook_exit
    setup: CustomMaterializationSetup = CustomMaterializationSetup(
        destination_qualified=destination_qualified,
        config=dict(entry.custom_config),
        placeholders=dict(entry.custom_placeholders),
    )
    materialization_outcome: CustomMaterializationPhaseOutcome = _run_custom_materialization(
        context=context,
        declared_columns=declared_columns,
        materialize_fn=materialize_fn,
        target=target,
        effective_vars=effective_vars,
        existing_relation=existing_relation,
        setup=setup,
        on_progress=on_progress,
        state=state,
    )
    if materialization_outcome.failure is not None:
        return materialization_outcome.failure
    materialization_result: MaterializationResult = cast(
        MaterializationResult, materialization_outcome.result
    )
    audit_outcome: CustomLifecyclePhaseOutcome = _run_custom_final_audits(
        context=context,
        materialization_result=materialization_result,
        state=state,
    )
    state = audit_outcome.state
    if audit_outcome.failure is not None:
        return audit_outcome.failure
    post_hook_exit: ModelExecutionResult | None = _run_custom_post_hooks(
        context=context,
        effective_vars=effective_vars,
        materialization_result=materialization_result,
        state=state,
    )
    if post_hook_exit is not None:
        return post_hook_exit
    return _complete_custom_materialization(
        context=context,
        materialization_result=materialization_result,
        state=state,
    )


def _run_custom_pre_hooks(
    *,
    context: ModelMaterializationContext,
    effective_vars: dict[str, object],
    state: CustomLifecycleState,
) -> ModelExecutionResult | None:
    entry: ModelPlanEntry = context.entry
    try:
        with diagnostics_context(sqlbuild_phase="pre_hook", sqlbuild_action_name="run"):
            pre_hook_skipped: bool = execute_hooks(
                connection=context.connection,
                adapter=context.adapter,
                hooks=entry.pre_hooks,
                phase=HookPhase.PRE_HOOKS,
                hook_functions=context.hook_functions,
                hook_results=state.hook_results,
                hook_run=HookRunContext(
                    model_name=entry.name,
                    destination=entry.destination,
                    run_id=context.run_id,
                    target=context.effective_target_name,
                    effective_vars=effective_vars,
                    statement_recorder=state.statement_recorder,
                    providers=context.providers,
                    python_identity_recorder=context.python_identity_recorder,
                ),
            )
        if pre_hook_skipped:
            return build_skipped_result(
                entry=entry,
                warnings=state.warnings,
                audit_results=state.audit_results,
                statement_recorder=state.statement_recorder,
                hook_results=state.hook_results,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.PRE_HOOK,
            error=str(exc),
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
            hook_results=state.hook_results,
        )
    return None


def _run_custom_materialization(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
    materialize_fn: Callable[[MaterializationContext], MaterializationResult],
    target: str,
    effective_vars: dict[str, object],
    existing_relation: RelationInfo | None,
    setup: CustomMaterializationSetup,
    on_progress: Callable[[str], None] | None,
    state: CustomLifecycleState,
) -> CustomMaterializationPhaseOutcome:
    entry: ModelPlanEntry = context.entry
    run_audits_fn: Callable[[str], tuple[AuditExecutionResult, ...]] = _build_run_audits(
        model_audits=context.model_audits,
        adapter=context.adapter,
        connection=context.connection,
        model_locations=context.model_locations,
        seed_locations=context.seed_locations,
        source_map=context.source_map,
        model_name=entry.name,
    )
    materialization_context: MaterializationContext = MaterializationContext(
        adapter=context.adapter,
        connection=context.connection,
        destination=setup.destination_qualified,
        destination_database=entry.destination.database,
        destination_schema=entry.destination.schema,
        destination_name=entry.destination.name,
        sql=entry.resolved_sql,
        config=setup.config,
        placeholders=setup.placeholders,
        existing_relation=existing_relation,
        run_id=context.run_id,
        build_target=target,
        vars=effective_vars,
        unique_key=entry.unique_key,
        declared_columns=declared_columns,
        is_first_run=existing_relation is None,
        is_full_refresh=entry.reason == PlanReason.FULL_REFRESH,
        query_changed=entry.reason == PlanReason.QUERY_CHANGED,
        schema_findings=entry.schema_findings,
        run_audits=run_audits_fn,
        on_progress=on_progress,
        logger=logging.getLogger(f"sqlbuild.materialization.{entry.name}"),
        statement_recorder=state.statement_recorder,
        providers=context.providers or _empty_provider_container(),
    )
    try:
        with diagnostics_context(sqlbuild_phase="materialize", sqlbuild_action_name="custom"):
            result: object = invoke_with_providers(
                function=materialize_fn,
                context=materialization_context,
                providers=context.providers,
            )
            materialization_result: MaterializationResult = cast(MaterializationResult, result)
    except Exception as exc:
        return CustomMaterializationPhaseOutcome(
            failure=build_failed_result(
                entry=entry,
                phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
                error=str(exc),
                warnings=state.warnings,
                audit_results=state.audit_results,
                statement_recorder=state.statement_recorder,
            )
        )
    if materialization_result.failed:
        user_audit_results: list[AuditExecutionResult] = (
            list(materialization_result.audit_results)
            if materialization_result.audit_results is not None
            else []
        )
        return CustomMaterializationPhaseOutcome(
            failure=build_failed_result(
                entry=entry,
                phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
                error=materialization_result.error or "custom materialization reported failure",
                warnings=state.warnings,
                audit_results=user_audit_results,
                statement_recorder=state.statement_recorder,
            )
        )
    return CustomMaterializationPhaseOutcome(result=materialization_result)


def _run_custom_final_audits(
    *,
    context: ModelMaterializationContext,
    materialization_result: MaterializationResult,
    state: CustomLifecycleState,
) -> CustomLifecyclePhaseOutcome:
    if materialization_result.audit_results is not None:
        return CustomLifecyclePhaseOutcome(
            state=replace(
                state,
                audit_results=[*state.audit_results, *materialization_result.audit_results],
            )
        )
    final_audit_run: FinalAuditRun = run_final_scope_audits(context=context)
    updated_state: CustomLifecycleState = replace(
        state,
        audit_results=[*state.audit_results, *final_audit_run.results],
    )
    if not final_audit_run.has_error:
        return CustomLifecyclePhaseOutcome(state=updated_state)
    _cleanup_relations(
        adapter=context.adapter,
        connection=context.connection,
        relations=materialization_result.cleanup_relations,
        keep=True,
        statement_recorder=updated_state.statement_recorder,
    )
    return CustomLifecyclePhaseOutcome(
        state=updated_state,
        failure=build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"final audit for '{context.entry.name}' failed after materialization "
                "with severity level: error"
            ),
            promoted_relation=materialization_result.relation,
            warnings=updated_state.warnings,
            audit_results=updated_state.audit_results,
            statement_recorder=updated_state.statement_recorder,
        ),
    )


def _run_custom_post_hooks(
    *,
    context: ModelMaterializationContext,
    effective_vars: dict[str, object],
    materialization_result: MaterializationResult,
    state: CustomLifecycleState,
) -> ModelExecutionResult | None:
    entry: ModelPlanEntry = context.entry
    try:
        with diagnostics_context(sqlbuild_phase="post_hook", sqlbuild_action_name="run"):
            post_hook_skipped: bool = execute_hooks(
                connection=context.connection,
                adapter=context.adapter,
                hooks=entry.post_hooks,
                phase=HookPhase.POST_HOOKS,
                hook_functions=context.hook_functions,
                hook_results=state.hook_results,
                hook_run=HookRunContext(
                    model_name=entry.name,
                    destination=entry.destination,
                    run_id=context.run_id,
                    target=context.effective_target_name,
                    effective_vars=effective_vars,
                    statement_recorder=state.statement_recorder,
                    providers=context.providers,
                    python_identity_recorder=context.python_identity_recorder,
                ),
            )
        if post_hook_skipped:
            _cleanup_relations(
                adapter=context.adapter,
                connection=context.connection,
                relations=materialization_result.cleanup_relations,
                keep=False,
                statement_recorder=state.statement_recorder,
            )
            return build_skipped_result(
                entry=entry,
                warnings=state.warnings,
                audit_results=state.audit_results,
                statement_recorder=state.statement_recorder,
                hook_results=state.hook_results,
                promoted_relation=materialization_result.relation,
            )
    except Exception as exc:
        _cleanup_relations(
            adapter=context.adapter,
            connection=context.connection,
            relations=materialization_result.cleanup_relations,
            keep=True,
            statement_recorder=state.statement_recorder,
        )
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.POST_HOOK,
            error=str(exc),
            promoted_relation=materialization_result.relation,
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
            hook_results=state.hook_results,
        )
    return None


def _complete_custom_materialization(
    *,
    context: ModelMaterializationContext,
    materialization_result: MaterializationResult,
    state: CustomLifecycleState,
) -> ModelExecutionResult:
    fingerprint_warnings: tuple[str, ...] = try_write_fingerprint(
        entry=context.entry,
        adapter=context.adapter,
        connection=context.connection,
        run_id=context.run_id,
        query_change_tracking=context.query_change_tracking,
        model_audits=context.model_audits,
        audit_results=tuple(state.audit_results),
    )
    _cleanup_relations(
        adapter=context.adapter,
        connection=context.connection,
        relations=materialization_result.cleanup_relations,
        keep=False,
        statement_recorder=state.statement_recorder,
    )
    return ModelExecutionResult(
        model_name=context.entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=materialization_result.relation,
        audit_results=tuple(state.audit_results),
        warning_messages=(*state.warnings, *fingerprint_warnings),
        lifecycle_events=state.statement_recorder.snapshot(),
        hook_results=tuple(state.hook_results),
    )


def _build_run_audits(
    *,
    model_audits: tuple[AuditPlanEntry, ...],
    adapter: BaseAdapter,
    connection: Any,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
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
                model_locations=model_locations,
                seed_locations=seed_locations,
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
                connection=connection,
                destination=relation,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        except Exception:
            pass
