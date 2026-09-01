"""Single-model table execution lifecycle."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import CursorBounds, ModelPlanEntry
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run._helpers.execution.final_audits import run_final_model_audits
from sqlbuild.executor.run._helpers.execution.hook_phases import run_post_hook_phase
from sqlbuild.executor.run._helpers.execution.hooks import execute_hooks, render_hooks
from sqlbuild.executor.run._helpers.execution.promotion import promote_relation_to_destination
from sqlbuild.executor.run._helpers.execution.results import (
    build_failed_result,
    build_skipped_result,
)
from sqlbuild.executor.run._helpers.execution.staging import create_staging_relation
from sqlbuild.executor.run._helpers.execution.table_targets import resolve_table_targets
from sqlbuild.executor.run._helpers.materializations.custom import (
    execute_custom_entry as execute_custom_entry,
)
from sqlbuild.executor.run._helpers.materializations.incremental import (
    execute_incremental_entry as execute_incremental_entry,
)
from sqlbuild.executor.run._helpers.materializations.microbatch import (
    execute_microbatch_entry as execute_microbatch_entry,
)
from sqlbuild.executor.run._helpers.materializations.snapshot import (
    execute_snapshot_entry as execute_snapshot_entry,
)
from sqlbuild.executor.run._helpers.materializations.view import (
    execute_view_entry as execute_view_entry,
)
from sqlbuild.executor.run._helpers.reuse.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run._helpers.validation.contracts import validate_runtime_contract
from sqlbuild.executor.run._helpers.validation.cursor_bounds import (
    build_runtime_cursor_spec,
    has_model_backed_cursor_watermarks,
    resolve_runtime_cursor_bounds,
    substitute_cursor_sentinels,
)
from sqlbuild.executor.run._helpers.validation.type_enforcement import enforce_types_staged
from sqlbuild.executor.run.models import (
    FinalAuditRun,
    HookExecutionResult,
    HookRunContext,
    ModelExecutionResult,
    ModelMaterializationContext,
    PostHookPhaseOutcome,
    TableLifecycleState,
    TableTargets,
)
from sqlbuild.executor.run.types import ExecutionPhase, HookPhase
from sqlbuild.executor.scheduling.types import ExecutionStatus


def execute_table_entry(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
    promotion_mode: TablePromotionMode,
    is_full_refresh: bool = False,
) -> ModelExecutionResult:
    """Execute one table model through its full materialization lifecycle."""

    entry: ModelPlanEntry = context.entry
    adapter: BaseAdapter = context.adapter
    connection: Any = context.connection
    targets: TableTargets = resolve_table_targets(adapter=adapter, entry=entry)
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []
    hook_results: list[HookExecutionResult] = []
    statement_recorder: StatementRecorder = StatementRecorder()
    runtime_owned_cursor_bounds: bool = not is_full_refresh and has_model_backed_cursor_watermarks(
        entry.cursor_input_relations
    )
    resolved_sql: str = entry.resolved_sql

    if runtime_owned_cursor_bounds:
        if entry.cursor_column is None:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error="runtime-owned cursor resolution requires cursor_column",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
            )
        try:
            runtime_bounds: CursorBounds | None = resolve_runtime_cursor_bounds(
                adapter=adapter,
                connection=connection,
                target_relation=targets.target_qualified,
                target_database=targets.target_database,
                target_schema=targets.target_schema,
                target_name=targets.target_table,
                spec=build_runtime_cursor_spec(entry=entry),
                watermark_resolver=context.watermark_resolver,
            )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"failed to resolve runtime cursor bounds: {exc}",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
                hook_results=hook_results,
            )
        if runtime_bounds is None:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"runtime cursor bounds could not be resolved for '{entry.name}'",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )
        resolved_sql = substitute_cursor_sentinels(sql=entry.resolved_sql, bounds=runtime_bounds)

    try:
        if not context.schema_prepared:
            adapter.ensure_schema(
                connection=connection,
                database=targets.target_database,
                schema=targets.target_schema,
                statement_recorder=statement_recorder,
            )
        statement_recorder.record_many(
            render_hooks(hooks=entry.pre_hooks, phase=HookPhase.PRE_HOOKS)
        )
        with diagnostics_context(sqlbuild_phase="pre_hook", sqlbuild_action_name="run"):
            pre_hook_skipped: bool = execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.pre_hooks,
                phase=HookPhase.PRE_HOOKS,
                hook_functions=context.hook_functions,
                hook_results=hook_results,
                hook_run=HookRunContext(
                    model_name=entry.name,
                    destination=entry.destination,
                    run_id=context.run_id,
                    target=context.effective_target_name,
                    effective_vars=context.effective_vars,
                    statement_recorder=statement_recorder,
                    providers=context.providers,
                    python_identity_recorder=context.python_identity_recorder,
                ),
            )
        if pre_hook_skipped:
            return build_skipped_result(
                entry=entry,
                warnings=warnings,
                audit_results=audit_results,
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

    state: TableLifecycleState = TableLifecycleState(
        warnings=warnings,
        audit_results=audit_results,
        statement_recorder=statement_recorder,
        hook_results=hook_results,
        resolved_sql=resolved_sql,
    )

    if promotion_mode == TablePromotionMode.STAGED:
        return _staged_lifecycle(
            context=context,
            targets=targets,
            state=state,
            declared_columns=declared_columns,
        )

    if entry.contract_enforced:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CONTRACT,
            error=ExecutorInputError(
                f"model '{entry.name}': contract enforced requires staged table promotion; "
                "immediate table promotion cannot validate runtime output before target mutation",
                code="K011",
            ),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    return _immediate_lifecycle(
        context=context,
        targets=targets,
        state=state,
        declared_columns=declared_columns,
    )


def _staged_lifecycle(
    *,
    context: ModelMaterializationContext,
    targets: TableTargets,
    state: TableLifecycleState,
    declared_columns: tuple[ColumnInfo, ...],
) -> ModelExecutionResult:
    """Staged table lifecycle: CTAS staging, type enforce, audit, promote."""

    entry: ModelPlanEntry = context.entry
    adapter: BaseAdapter = context.adapter
    connection: Any = context.connection
    target_qualified: str = targets.target_qualified
    staging_qualified: str = targets.staging_qualified
    warnings: list[str] = state.warnings
    audit_results: list[AuditExecutionResult] = state.audit_results
    statement_recorder: StatementRecorder = state.statement_recorder
    hook_results: list[HookExecutionResult] = state.hook_results
    try:
        with diagnostics_context(
            sqlbuild_phase="materialize", sqlbuild_action_name="create_staging"
        ):
            reuse_origin_fingerprint: Fingerprint | None = create_staging_relation(
                context=context,
                staging_qualified=staging_qualified,
                resolved_sql=state.resolved_sql,
                statement_recorder=statement_recorder,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.STAGING,
            error=str(exc),
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    if entry.type_enforcement and declared_columns:
        try:
            with diagnostics_context(
                sqlbuild_phase="type_enforcement", sqlbuild_action_name="rebuild_staging"
            ):
                enforce_types_staged(
                    adapter=adapter,
                    connection=connection,
                    staging_qualified=staging_qualified,
                    staging_database=targets.target_database,
                    staging_schema=targets.target_schema,
                    staging_table=targets.staging_table,
                    declared_columns=declared_columns,
                    table_type=entry.table_type,
                    statement_recorder=statement_recorder,
                )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.TYPE_ENFORCEMENT,
                error=str(exc),
                staging_relation=staging_qualified,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )

    try:
        with diagnostics_context(
            sqlbuild_phase="contract", sqlbuild_action_name="validate_staging"
        ):
            staging_columns: tuple[ColumnInfo, ...] = adapter.get_columns(
                connection=connection,
                database=targets.target_database,
                schema=targets.target_schema,
                name=targets.staging_table,
            )
            validate_runtime_contract(
                entry=entry,
                actual_columns=staging_columns,
                dialect=adapter.sql_analysis_dialect_name,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CONTRACT,
            error=exc,
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    final_audit_run: FinalAuditRun = run_final_model_audits(
        relation_overrides={entry.name: staging_qualified},
        model_audits=context.model_audits,
        reuse_origin_fingerprint=reuse_origin_fingerprint,
        adapter=adapter,
        connection=connection,
        model_locations=context.model_locations,
        seed_locations=context.seed_locations,
        source_map=context.source_map,
    )
    audit_results.extend(final_audit_run.results)

    if final_audit_run.has_error:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"final audit for '{entry.name}' failed before replacing target table "
                "with severity level: error"
            ),
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    try:
        with diagnostics_context(sqlbuild_phase="promote", sqlbuild_action_name="check_existing"):
            _ = promote_relation_to_destination(
                adapter=adapter,
                connection=connection,
                origin_relation=staging_qualified,
                destination_relation=target_qualified,
                destination_database=targets.target_database,
                destination_schema=targets.target_schema,
                destination_name=targets.target_table,
                statement_recorder=statement_recorder,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.PROMOTION,
            error=str(exc),
            staging_relation=staging_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    post_hook_outcome: PostHookPhaseOutcome = run_post_hook_phase(
        context=context,
        warnings=warnings,
        audit_results=audit_results,
        hook_results=hook_results,
        statement_recorder=statement_recorder,
        promoted_relation=target_qualified,
    )
    if post_hook_outcome.failure is not None:
        return post_hook_outcome.failure
    if post_hook_outcome.skipped:
        return build_skipped_result(
            entry=entry,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
            promoted_relation=target_qualified,
        )

    fingerprint_warnings: tuple[str, ...] = try_write_fingerprint(
        entry=entry,
        adapter=adapter,
        connection=connection,
        run_id=context.run_id,
        query_change_tracking=context.query_change_tracking,
        model_audits=context.model_audits,
        audit_results=tuple(audit_results),
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=target_qualified,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings) + fingerprint_warnings,
        lifecycle_events=statement_recorder.snapshot(),
        hook_results=tuple(hook_results),
    )


def _immediate_lifecycle(
    *,
    context: ModelMaterializationContext,
    targets: TableTargets,
    state: TableLifecycleState,
    declared_columns: tuple[ColumnInfo, ...],
) -> ModelExecutionResult:
    """Immediate table lifecycle: CTAS target, audit after, no staging."""

    entry: ModelPlanEntry = context.entry
    adapter: BaseAdapter = context.adapter
    connection: Any = context.connection
    target_qualified: str = targets.target_qualified
    warnings: list[str] = state.warnings
    audit_results: list[AuditExecutionResult] = state.audit_results
    statement_recorder: StatementRecorder = state.statement_recorder
    hook_results: list[HookExecutionResult] = state.hook_results
    reuse_origin_fingerprint: Fingerprint | None = None
    if entry.type_enforcement and declared_columns:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.TYPE_ENFORCEMENT,
            error=(
                f"model '{entry.name}': type enforcement requires staged promotion mode "
                f"for runtime column inspection; set table_promotion_mode: staged in "
                f"sqlbuild_project.toml settings"
            ),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    try:
        with diagnostics_context(sqlbuild_phase="materialize", sqlbuild_action_name="create_table"):
            adapter.create_table_as(
                connection=connection,
                destination=target_qualified,
                sql=state.resolved_sql,
                config={"table_type": entry.table_type},
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

    immediate_audit_run: FinalAuditRun = run_final_model_audits(
        relation_overrides=None,
        model_audits=context.model_audits,
        reuse_origin_fingerprint=reuse_origin_fingerprint,
        adapter=adapter,
        connection=connection,
        model_locations=context.model_locations,
        seed_locations=context.seed_locations,
        source_map=context.source_map,
    )
    audit_results.extend(immediate_audit_run.results)

    if immediate_audit_run.has_error:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"final audit for '{entry.name}' failed after target table was replaced "
                "with severity level: error"
            ),
            promoted_relation=target_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
        )

    post_hook_outcome: PostHookPhaseOutcome = run_post_hook_phase(
        context=context,
        warnings=warnings,
        audit_results=audit_results,
        hook_results=hook_results,
        statement_recorder=statement_recorder,
        promoted_relation=target_qualified,
    )
    if post_hook_outcome.failure is not None:
        return post_hook_outcome.failure
    if post_hook_outcome.skipped:
        return build_skipped_result(
            entry=entry,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
            promoted_relation=target_qualified,
        )

    fingerprint_warnings: tuple[str, ...] = try_write_fingerprint(
        entry=entry,
        adapter=adapter,
        connection=connection,
        run_id=context.run_id,
        query_change_tracking=context.query_change_tracking,
        model_audits=context.model_audits,
        audit_results=tuple(audit_results),
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=target_qualified,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings) + fingerprint_warnings,
        lifecycle_events=statement_recorder.snapshot(),
        hook_results=tuple(hook_results),
    )
