"""Microbatch incremental execution lifecycle."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    CursorInputRelation,
    ModelPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    CursorGrain,
    CursorType,
    IncrementalStrategy,
    OnSchemaChange,
)
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run._helpers.execution.final_audits import (
    run_delta_scope_audits,
    run_final_scope_audits,
)
from sqlbuild.executor.run._helpers.execution.hook_phases import (
    run_post_hook_phase,
    run_pre_hook_phase,
)
from sqlbuild.executor.run._helpers.execution.results import (
    build_failed_result,
    build_skipped_result,
)
from sqlbuild.executor.run._helpers.materializations.incremental import (
    _apply_schema_change,
    _execute_dml,
)
from sqlbuild.executor.run._helpers.reuse.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run._helpers.validation.cursor_bounds import (
    has_model_backed_cursor_inputs,
    resolve_effective_timestamp_grain,
    resolve_runtime_cursor_bounds,
)
from sqlbuild.executor.run._helpers.validation.type_enforcement import enforce_types_staged
from sqlbuild.executor.run.models import (
    BatchWindow,
    FinalAuditRun,
    MicrobatchLifecycleState,
    MicrobatchPhaseOutcome,
    MicrobatchSchemaPhaseOutcome,
    MicrobatchTargets,
    ModelExecutionResult,
    ModelMaterializationContext,
    PostHookPhaseOutcome,
    RuntimeCursorSpec,
)
from sqlbuild.executor.run.types import ExecutionPhase
from sqlbuild.executor.scheduling.types import ExecutionStatus

_DEFAULT_ON_SCHEMA_CHANGE: OnSchemaChange = OnSchemaChange.APPEND_NEW_COLUMNS
_DURATION_PATTERN_STR: str = (
    r"^(?:(\d+)y)?(?:(\d+)mo)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"
)
_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


@dataclass(frozen=True)
class _MicrobatchPlan:
    """Planned batch windows or the early-exit result when none can run."""

    batches: tuple[BatchWindow, ...] = ()
    early_exit: ModelExecutionResult | None = None


def execute_microbatch_entry(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
    is_full_refresh: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> ModelExecutionResult:
    """Execute one microbatch incremental model through batched delta/DML."""

    targets: MicrobatchTargets = _resolve_microbatch_targets(context=context)
    state: MicrobatchLifecycleState = MicrobatchLifecycleState(
        warnings=[],
        audit_results=[],
        hook_results=[],
        statement_recorder=StatementRecorder(),
    )
    pre_hook_exit: ModelExecutionResult | None = run_pre_hook_phase(
        context=context,
        warnings=state.warnings,
        audit_results=state.audit_results,
        hook_results=state.hook_results,
        statement_recorder=state.statement_recorder,
    )
    if pre_hook_exit is not None:
        return pre_hook_exit
    batch_plan: _MicrobatchPlan = _plan_microbatch_windows(
        context=context,
        is_full_refresh=is_full_refresh,
        target_qualified=targets.target_qualified,
        warnings=state.warnings,
        audit_results=state.audit_results,
        statement_recorder=state.statement_recorder,
    )
    if batch_plan.early_exit is not None:
        return batch_plan.early_exit
    full_refresh_exit: ModelExecutionResult | None = _drop_target_for_full_refresh(
        context=context,
        is_full_refresh=is_full_refresh,
        target_qualified=targets.target_qualified,
        warnings=state.warnings,
        audit_results=state.audit_results,
        statement_recorder=state.statement_recorder,
    )
    if full_refresh_exit is not None:
        return full_refresh_exit
    batch_outcome: MicrobatchPhaseOutcome = _execute_microbatch_batches(
        context=context,
        declared_columns=declared_columns,
        is_full_refresh=is_full_refresh,
        batches=batch_plan.batches,
        targets=targets,
        state=state,
        on_progress=on_progress,
    )
    state = batch_outcome.state
    if batch_outcome.failure is not None:
        return replace(
            batch_outcome.failure,
            batch_count=batch_outcome.completed_batches,
            rows_affected=batch_outcome.rows_affected,
        )
    final_audit_run: FinalAuditRun = run_final_scope_audits(context=context)
    state.audit_results.extend(final_audit_run.results)
    if final_audit_run.has_error:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"final audit for '{context.entry.name}' failed after target update "
                "with severity level: error"
            ),
            promoted_relation=targets.target_qualified,
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    post_hook_outcome: PostHookPhaseOutcome = run_post_hook_phase(
        context=context,
        warnings=state.warnings,
        audit_results=state.audit_results,
        hook_results=state.hook_results,
        statement_recorder=state.statement_recorder,
        promoted_relation=targets.target_qualified,
    )
    if post_hook_outcome.failure is not None:
        return post_hook_outcome.failure
    if post_hook_outcome.skipped:
        return build_skipped_result(
            entry=context.entry,
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
            hook_results=state.hook_results,
            promoted_relation=targets.target_qualified,
        )
    state.warnings.extend(
        try_write_fingerprint(
            entry=context.entry,
            adapter=context.adapter,
            connection=context.connection,
            run_id=context.run_id,
            query_change_tracking=context.query_change_tracking,
            model_audits=context.model_audits,
            audit_results=tuple(state.audit_results),
        )
    )
    resolved_range: CursorBounds | None = context.entry.microbatch_range
    return ModelExecutionResult(
        model_name=context.entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=targets.target_qualified,
        batch_count=batch_outcome.completed_batches,
        rows_affected=batch_outcome.rows_affected,
        cursor_range_start=None if resolved_range is None else resolved_range.start,
        cursor_range_end=None if resolved_range is None else resolved_range.end,
        cursor_type=context.entry.cursor_type,
        cursor_grain=context.entry.cursor_grain,
        audit_results=tuple(state.audit_results),
        warning_messages=tuple(state.warnings),
        lifecycle_events=state.statement_recorder.snapshot(),
        hook_results=tuple(state.hook_results),
    )


def _resolve_microbatch_targets(*, context: ModelMaterializationContext) -> MicrobatchTargets:
    entry: ModelPlanEntry = context.entry
    target_table: str = entry.destination.name
    delta_table: str = f"{target_table}__delta"
    return MicrobatchTargets(
        target_database=entry.destination.database,
        target_schema=entry.destination.schema,
        target_table=target_table,
        target_qualified=resolve_relation_location_qualified_name(
            adapter=context.adapter,
            location=entry.destination,
        ),
        delta_table=delta_table,
        delta_qualified=resolve_qualified_name_parts(
            adapter=context.adapter,
            database=entry.destination.database,
            schema=entry.destination.schema,
            name=delta_table,
        ),
    )


def _execute_microbatch_batches(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
    is_full_refresh: bool,
    batches: tuple[BatchWindow, ...],
    targets: MicrobatchTargets,
    state: MicrobatchLifecycleState,
    on_progress: Callable[[str], None] | None = None,
) -> MicrobatchPhaseOutcome:
    schema_checked: bool = False
    completed_batches: int = 0
    total_rows: int = 0
    total_batches: int = len(batches)
    batch: BatchWindow
    for batch in batches:
        batch_start_time: float = time.monotonic()
        window_text: str = f"{batch.start}..{batch.end}"
        stage_failure: ModelExecutionResult | None = _stage_microbatch_delta(
            context=context,
            batch=batch,
            window_text=window_text,
            targets=targets,
            state=state,
        )
        if stage_failure is not None:
            return MicrobatchPhaseOutcome(
                state=state, failure=stage_failure, completed_batches=completed_batches
            )
        schema_outcome: MicrobatchSchemaPhaseOutcome = _apply_microbatch_schema_change(
            context=context,
            is_full_refresh=is_full_refresh,
            schema_checked=schema_checked,
            window_text=window_text,
            targets=targets,
            state=state,
        )
        state = schema_outcome.state
        if schema_outcome.failure is not None:
            return MicrobatchPhaseOutcome(
                state=state, failure=schema_outcome.failure, completed_batches=completed_batches
            )
        schema_checked = schema_outcome.schema_checked
        type_failure: ModelExecutionResult | None = _enforce_microbatch_types(
            context=context,
            declared_columns=declared_columns,
            batch=batch,
            window_text=window_text,
            targets=targets,
            state=state,
        )
        if type_failure is not None:
            return MicrobatchPhaseOutcome(
                state=state, failure=type_failure, completed_batches=completed_batches
            )
        audit_outcome: MicrobatchPhaseOutcome = _run_microbatch_delta_audits(
            context=context,
            batch=batch,
            targets=targets,
            state=state,
        )
        state = audit_outcome.state
        if audit_outcome.failure is not None:
            return replace(audit_outcome, completed_batches=completed_batches)
        dml_result: ModelExecutionResult | int | None = _apply_microbatch_dml(
            context=context,
            batch=batch,
            completed_batches=completed_batches,
            is_full_refresh=is_full_refresh,
            window_text=window_text,
            targets=targets,
            state=state,
        )
        if isinstance(dml_result, ModelExecutionResult):
            return MicrobatchPhaseOutcome(
                state=state,
                failure=dml_result,
                completed_batches=completed_batches,
                rows_affected=total_rows if total_rows > 0 else None,
            )
        if isinstance(dml_result, int):
            total_rows += dml_result
        _complete_microbatch_batch(
            context=context,
            window_text=window_text,
            targets=targets,
            state=state,
        )
        completed_batches += 1
        if on_progress is not None:
            batch_elapsed: float = time.monotonic() - batch_start_time
            on_progress(
                f"batch {completed_batches}/{total_batches} {window_text} {batch_elapsed:.1f}s"
            )
    return MicrobatchPhaseOutcome(
        state=state,
        completed_batches=completed_batches,
        rows_affected=total_rows if total_rows > 0 else None,
    )


def _stage_microbatch_delta(
    *,
    context: ModelMaterializationContext,
    batch: BatchWindow,
    window_text: str,
    targets: MicrobatchTargets,
    state: MicrobatchLifecycleState,
) -> ModelExecutionResult | None:
    log_debug_event(
        logger=_DEBUG_LOGGER,
        message="",
        sqlbuild_subject="model",
        sqlbuild_name=context.entry.name,
        sqlbuild_event="batch_start",
        sqlbuild_phase="batch",
        sqlbuild_window=window_text,
    )
    batch_sql: str = _substitute_sentinels(
        sql=context.entry.resolved_sql,
        batch_start=batch.start,
        batch_end=batch.end,
    )
    try:
        with diagnostics_context(
            sqlbuild_phase="materialize",
            sqlbuild_action_name="create_delta",
            sqlbuild_window=window_text,
        ):
            context.adapter.drop(
                connection=context.connection,
                destination=targets.delta_qualified,
                if_exists=True,
                statement_recorder=state.statement_recorder,
            )
            context.adapter.create_table_as(
                connection=context.connection,
                destination=targets.delta_qualified,
                sql=batch_sql,
                statement_recorder=state.statement_recorder,
            )
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.STAGING,
            error=f"batch {batch.index}: {exc}",
            staging_relation=targets.delta_qualified,
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    return None


def _apply_microbatch_schema_change(
    *,
    context: ModelMaterializationContext,
    is_full_refresh: bool,
    schema_checked: bool,
    window_text: str,
    targets: MicrobatchTargets,
    state: MicrobatchLifecycleState,
) -> MicrobatchSchemaPhaseOutcome:
    if schema_checked or is_full_refresh:
        return MicrobatchSchemaPhaseOutcome(state=state, schema_checked=schema_checked)
    try:
        with diagnostics_context(
            sqlbuild_phase="schema_change",
            sqlbuild_action_name="inspect",
            sqlbuild_window=window_text,
        ):
            delta_columns: tuple[ColumnInfo, ...] = context.adapter.get_columns(
                connection=context.connection,
                database=targets.target_database,
                schema=targets.target_schema,
                name=targets.delta_table,
            )
            target_columns: tuple[ColumnInfo, ...] = context.adapter.get_columns(
                connection=context.connection,
                database=targets.target_database,
                schema=targets.target_schema,
                name=targets.target_table,
            )
            schema_warnings: tuple[str, ...] = _apply_schema_change(
                adapter=context.adapter,
                connection=context.connection,
                target_qualified=targets.target_qualified,
                target_columns=target_columns,
                delta_columns=delta_columns,
                on_schema_change=context.entry.on_schema_change or _DEFAULT_ON_SCHEMA_CHANGE,
                statement_recorder=state.statement_recorder,
            )
    except Exception as exc:
        return MicrobatchSchemaPhaseOutcome(
            state=state,
            schema_checked=False,
            failure=build_failed_result(
                entry=context.entry,
                phase=ExecutionPhase.SCHEMA_CHANGE,
                error=str(exc),
                staging_relation=targets.delta_qualified,
                warnings=state.warnings,
                audit_results=state.audit_results,
                statement_recorder=state.statement_recorder,
            ),
        )
    return MicrobatchSchemaPhaseOutcome(
        state=replace(state, warnings=[*state.warnings, *schema_warnings]),
        schema_checked=True,
    )


def _enforce_microbatch_types(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
    batch: BatchWindow,
    window_text: str,
    targets: MicrobatchTargets,
    state: MicrobatchLifecycleState,
) -> ModelExecutionResult | None:
    if not context.entry.type_enforcement or not declared_columns:
        return None
    try:
        with diagnostics_context(
            sqlbuild_phase="type_enforcement",
            sqlbuild_action_name="rebuild_delta",
            sqlbuild_window=window_text,
        ):
            enforce_types_staged(
                adapter=context.adapter,
                connection=context.connection,
                staging_qualified=targets.delta_qualified,
                staging_database=targets.target_database,
                staging_schema=targets.target_schema,
                staging_table=targets.delta_table,
                declared_columns=declared_columns,
                statement_recorder=state.statement_recorder,
            )
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.TYPE_ENFORCEMENT,
            error=f"batch {batch.index}: {exc}",
            staging_relation=targets.delta_qualified,
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    return None


def _run_microbatch_delta_audits(
    *,
    context: ModelMaterializationContext,
    batch: BatchWindow,
    targets: MicrobatchTargets,
    state: MicrobatchLifecycleState,
) -> MicrobatchPhaseOutcome:
    delta_audit_run: FinalAuditRun = run_delta_scope_audits(
        context=context,
        delta_qualified=targets.delta_qualified,
    )
    updated_state: MicrobatchLifecycleState = replace(
        state,
        audit_results=[*state.audit_results, *delta_audit_run.results],
    )
    if not delta_audit_run.has_error:
        return MicrobatchPhaseOutcome(state=updated_state)
    return MicrobatchPhaseOutcome(
        state=updated_state,
        failure=build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"batch {batch.index}: delta audit for '{context.entry.name}' failed before "
                "target update with severity level: error"
            ),
            staging_relation=targets.delta_qualified,
            warnings=updated_state.warnings,
            audit_results=updated_state.audit_results,
            statement_recorder=updated_state.statement_recorder,
        ),
    )


def _apply_microbatch_dml(
    *,
    context: ModelMaterializationContext,
    batch: BatchWindow,
    completed_batches: int,
    is_full_refresh: bool,
    window_text: str,
    targets: MicrobatchTargets,
    state: MicrobatchLifecycleState,
) -> ModelExecutionResult | int | None:
    try:
        with diagnostics_context(
            sqlbuild_phase="dml",
            sqlbuild_action_name="apply",
            sqlbuild_window=window_text,
        ):
            target_columns: tuple[ColumnInfo, ...] = (
                context.adapter.get_columns(
                    connection=context.connection,
                    database=targets.target_database,
                    schema=targets.target_schema,
                    name=targets.target_table,
                )
                if not is_full_refresh or completed_batches > 0
                else ()
            )
            delta_columns: tuple[ColumnInfo, ...] = context.adapter.get_columns(
                connection=context.connection,
                database=targets.target_database,
                schema=targets.target_schema,
                name=targets.delta_table,
            )
            _validate_cursor_output_columns(entry=context.entry, delta_columns=delta_columns)
            batch_rows: int | None = None
            if is_full_refresh and completed_batches == 0:
                context.adapter.create_table_as(
                    connection=context.connection,
                    destination=targets.target_qualified,
                    sql=f"SELECT * FROM {targets.delta_qualified}",
                    statement_recorder=state.statement_recorder,
                )
            else:
                batch_rows = _execute_dml(
                    adapter=context.adapter,
                    connection=context.connection,
                    target_qualified=targets.target_qualified,
                    delta_qualified=targets.delta_qualified,
                    target_columns=target_columns,
                    delta_columns=delta_columns,
                    entry=context.entry,
                    cursor_start=batch.start,
                    cursor_end=batch.end,
                    statement_recorder=state.statement_recorder,
                )
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.DML,
            error=f"batch {batch.index}: {exc}",
            staging_relation=targets.delta_qualified,
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    return batch_rows


def _complete_microbatch_batch(
    *,
    context: ModelMaterializationContext,
    window_text: str,
    targets: MicrobatchTargets,
    state: MicrobatchLifecycleState,
) -> None:
    with diagnostics_context(
        sqlbuild_phase="cleanup",
        sqlbuild_action_name="drop_delta",
        sqlbuild_window=window_text,
    ):
        context.adapter.drop(
            connection=context.connection,
            destination=targets.delta_qualified,
            if_exists=True,
            statement_recorder=state.statement_recorder,
        )
    log_debug_event(
        logger=_DEBUG_LOGGER,
        message="",
        sqlbuild_subject="model",
        sqlbuild_name=context.entry.name,
        sqlbuild_event="batch_complete",
        sqlbuild_phase="batch",
        sqlbuild_window=window_text,
        sqlbuild_status="ok",
    )


def _drop_target_for_full_refresh(
    *,
    context: ModelMaterializationContext,
    is_full_refresh: bool,
    target_qualified: str,
    warnings: list[str],
    audit_results: list[AuditExecutionResult],
    statement_recorder: StatementRecorder,
) -> ModelExecutionResult | None:
    """Drop the target before a full-refresh run; return a failure result on error."""

    if not is_full_refresh:
        return None
    try:
        with diagnostics_context(sqlbuild_phase="cleanup", sqlbuild_action_name="drop_target"):
            context.adapter.drop(
                connection=context.connection,
                destination=target_qualified,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.STAGING,
            error=f"failed to drop target for full-refresh microbatch: {exc}",
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )
    return None


def _plan_microbatch_windows(
    *,
    context: ModelMaterializationContext,
    is_full_refresh: bool,
    target_qualified: str,
    warnings: list[str],
    audit_results: list[AuditExecutionResult],
    statement_recorder: StatementRecorder,
) -> _MicrobatchPlan:
    """Resolve the microbatch cursor range and compute batch windows."""

    entry: ModelPlanEntry = context.entry
    adapter: BaseAdapter = context.adapter
    connection: Any = context.connection
    runtime_owned_cursor_bounds: bool = has_model_backed_cursor_inputs(entry.cursor_input_relations)
    microbatch_range: CursorBounds | None = entry.microbatch_range
    if runtime_owned_cursor_bounds:
        if entry.cursor_column is None:
            return _MicrobatchPlan(
                early_exit=build_failed_result(
                    entry=entry,
                    phase=ExecutionPhase.STAGING,
                    error="runtime-owned cursor resolution requires cursor_column",
                    warnings=warnings,
                    audit_results=audit_results,
                    statement_recorder=statement_recorder,
                )
            )
        try:
            microbatch_range = resolve_runtime_cursor_bounds(
                adapter=adapter,
                connection=connection,
                target_relation=target_qualified,
                target_database=entry.destination.database,
                target_schema=entry.destination.schema,
                target_name=entry.destination.name,
                spec=RuntimeCursorSpec(
                    cursor_column=entry.cursor_column,
                    cursor_type=entry.cursor_type,
                    cursor_grain=entry.cursor_grain,
                    cursor_start=entry.cursor_start,
                    cursor_input_relations=entry.cursor_input_relations,
                ),
            )
        except Exception as exc:
            return _MicrobatchPlan(
                early_exit=build_failed_result(
                    entry=entry,
                    phase=ExecutionPhase.STAGING,
                    error=f"failed to discover runtime microbatch cursor range: {exc}",
                    warnings=warnings,
                    audit_results=audit_results,
                    statement_recorder=statement_recorder,
                )
            )
    elif is_full_refresh:
        try:
            microbatch_range = _discover_cursor_range(
                adapter=adapter,
                connection=connection,
                cursor_type=entry.cursor_type,
                cursor_start=entry.cursor_start,
                cursor_input_relations=entry.cursor_input_relations,
            )
        except Exception as exc:
            return _MicrobatchPlan(
                early_exit=build_failed_result(
                    entry=entry,
                    phase=ExecutionPhase.STAGING,
                    error=f"failed to discover microbatch cursor range: {exc}",
                    warnings=warnings,
                    audit_results=audit_results,
                    statement_recorder=statement_recorder,
                )
            )
        if microbatch_range is None:
            return _MicrobatchPlan(
                early_exit=ModelExecutionResult(
                    model_name=entry.name,
                    status=ExecutionStatus.SUCCESS,
                    promoted_relation=target_qualified,
                    audit_results=tuple(audit_results),
                    warning_messages=(
                        *tuple(warnings),
                        "microbatch range is empty; no batches to process",
                    ),
                    lifecycle_events=statement_recorder.snapshot(),
                )
            )

    if microbatch_range is None:
        return _MicrobatchPlan(
            early_exit=build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error="microbatch_range is not available and model is not full refresh",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )
        )

    batch_size: str | None = entry.batch_size
    cursor_type: str | None = entry.cursor_type
    if batch_size is None or cursor_type is None:
        return _MicrobatchPlan(
            early_exit=build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error="microbatch requires batch_size and cursor_type",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )
        )

    effective_batch_size: str = batch_size
    if runtime_owned_cursor_bounds:
        effective_timestamp_grain: str | None = resolve_effective_timestamp_grain(
            cursor_type=cursor_type,
            downstream_grain=entry.cursor_grain,
            cursor_input_relations=entry.cursor_input_relations,
        )
        if effective_timestamp_grain is not None:
            effective_batch_size = _coarsen_timestamp_batch_size(
                batch_size=batch_size,
                effective_grain=effective_timestamp_grain,
            )

    batches: tuple[BatchWindow, ...] = compute_batch_windows(
        start=microbatch_range.start,
        end=microbatch_range.end,
        batch_size=effective_batch_size,
        cursor_type=cursor_type,
    )

    if not batches:
        return _MicrobatchPlan(
            early_exit=ModelExecutionResult(
                model_name=entry.name,
                status=ExecutionStatus.SUCCESS,
                promoted_relation=target_qualified,
                audit_results=tuple(audit_results),
                warning_messages=(*tuple(warnings), "no batches to process"),
                lifecycle_events=statement_recorder.snapshot(),
            )
        )
    return _MicrobatchPlan(batches=batches)


def compute_batch_windows(
    *,
    start: str,
    end: str,
    batch_size: str,
    cursor_type: str,
) -> tuple[BatchWindow, ...]:
    """Split a cursor range into ordered batch windows."""

    if cursor_type == CursorType.TIMESTAMP:
        return _compute_timestamp_batches(start=start, end=end, batch_size=batch_size)
    if cursor_type == CursorType.INTEGER:
        return _compute_integer_batches(start=start, end=end, batch_size=batch_size)
    return ()


def _substitute_sentinels(
    *,
    sql: str,
    batch_start: str,
    batch_end: str,
) -> str:
    """Replace microbatch cursor sentinels with concrete batch bounds."""

    result: str = sql.replace(MICROBATCH_START_SENTINEL, batch_start)
    result = result.replace(MICROBATCH_END_SENTINEL, batch_end)
    return result


def _advance_discovered_end_bound(*, raw_max: Any) -> str:
    """Step the discovered end bound past MAX(cursor) so the final value is included."""

    if isinstance(raw_max, datetime):
        return (raw_max + timedelta(seconds=1)).isoformat()
    if isinstance(raw_max, date):
        return (raw_max + timedelta(days=1)).isoformat()
    if isinstance(raw_max, (int, Decimal)):
        return str(int(raw_max) + 1)
    raise ExecutorInputError(
        f"microbatch cursor discovery returned an unsupported cursor type "
        f"'{type(raw_max).__name__}'; the end bound cannot be advanced safely, so the "
        "newest cursor value would be dropped from every run"
    )


def _discover_cursor_range(
    *,
    adapter: BaseAdapter,
    connection: Any,
    cursor_type: str | None,
    cursor_start: str | None,
    cursor_input_relations: tuple[CursorInputRelation, ...],
) -> CursorBounds | None:
    """Discover MIN/MAX cursor range from cursor-bearing input relations."""

    if not cursor_input_relations:
        return None
    parts: list[str] = []
    cursor_input: CursorInputRelation
    for cursor_input in cursor_input_relations:
        parts.append(
            f"SELECT MIN({cursor_input.cursor_column}) AS _min, "
            f"MAX({cursor_input.cursor_column}) AS _max FROM {cursor_input.relation}"
        )
    discovery_sql: str = "SELECT MIN(_min), MAX(_max) FROM (" + " UNION ALL ".join(parts) + ")"
    cursor: Any = adapter.execute(connection=connection, sql=discovery_sql)
    row: Any = cursor.fetchone()
    if row is None or row[0] is None or row[1] is None:
        return None
    raw_min: Any = row[0]
    raw_max: Any = row[1]
    min_val: str = raw_min.isoformat() if isinstance(raw_min, datetime) else str(raw_min)
    max_val: str = _advance_discovered_end_bound(raw_max=raw_max)
    if cursor_start is not None:
        if cursor_type == CursorType.TIMESTAMP:
            start_dt: datetime = datetime.fromisoformat(min_val)
            floor_dt: datetime = datetime.fromisoformat(cursor_start)
            min_val = max(start_dt, floor_dt).isoformat()
        elif cursor_type == CursorType.INTEGER:
            min_val = str(max(int(min_val), int(cursor_start)))
    return CursorBounds(start=min_val, end=max_val)


def _validate_cursor_output_columns(
    *,
    entry: ModelPlanEntry,
    delta_columns: tuple[ColumnInfo, ...],
) -> None:
    """Validate cursor-based microbatch DML can address the model output cursor."""

    if entry.incremental_strategy != IncrementalStrategy.DELETE_INSERT:
        return
    cursor_column: str | None = entry.cursor_column
    if cursor_column is None:
        return
    delta_names: frozenset[str] = frozenset(column.name.lower() for column in delta_columns)
    if cursor_column.lower() in delta_names:
        return
    raise ExecutorInputError(
        f"microbatch cursor column '{cursor_column}' is not produced by model output; "
        "use cursor_inputs for upstream cursor columns and set cursor to the target output "
        "cursor column"
    )


def _compute_timestamp_batches(
    *,
    start: str,
    end: str,
    batch_size: str,
) -> tuple[BatchWindow, ...]:
    """Split a timestamp range into batch windows by duration."""

    import re

    pattern: re.Pattern[str] = re.compile(_DURATION_PATTERN_STR)
    match: re.Match[str] | None = pattern.match(batch_size)
    if match is None:
        return ()
    years: int = int(match.group(1) or 0)
    months: int = int(match.group(2) or 0)
    days: int = int(match.group(3) or 0)
    hours: int = int(match.group(4) or 0)
    minutes: int = int(match.group(5) or 0)
    seconds: int = int(match.group(6) or 0)
    if years == months == days == hours == minutes == seconds == 0:
        return ()

    try:
        start_dt: datetime = datetime.fromisoformat(start)
        end_dt: datetime = datetime.fromisoformat(end)
    except (ValueError, TypeError):
        return ()

    if start_dt >= end_dt:
        return ()

    windows: list[BatchWindow] = []
    index: int = 0
    current: datetime = start_dt
    while current < end_dt:
        batch_end_candidate: datetime = _add_timestamp_interval(
            current=current,
            years=years,
            months=months,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
        )
        batch_end: datetime = min(batch_end_candidate, end_dt)
        windows.append(
            BatchWindow(
                start=current.isoformat(),
                end=batch_end.isoformat(),
                index=index,
            )
        )
        current = batch_end
        index += 1

    return tuple(windows)


def _compute_integer_batches(
    *,
    start: str,
    end: str,
    batch_size: str,
) -> tuple[BatchWindow, ...]:
    """Split an integer range into batch windows."""

    try:
        start_int: int = int(Decimal(start))
        end_int: int = int(Decimal(end))
        size_int: int = int(Decimal(batch_size))
    except (InvalidOperation, ValueError, OverflowError):
        return ()

    if size_int <= 0 or start_int >= end_int:
        return ()

    windows: list[BatchWindow] = []
    index: int = 0
    current: int = start_int
    while current < end_int:
        batch_end: int = min(current + size_int, end_int)
        windows.append(
            BatchWindow(
                start=str(current),
                end=str(batch_end),
                index=index,
            )
        )
        current = batch_end
        index += 1

    return tuple(windows)


def _coarsen_timestamp_batch_size(*, batch_size: str, effective_grain: str) -> str:
    grain_sizes: dict[str, tuple[int, str]] = {
        CursorGrain.SECOND: (0, "1s"),
        CursorGrain.MINUTE: (1, "1m"),
        CursorGrain.HOUR: (2, "1h"),
        CursorGrain.DAY: (3, "1d"),
        CursorGrain.MONTH: (4, "1mo"),
        CursorGrain.YEAR: (5, "1y"),
    }
    parsed_order: int | None = _timestamp_batch_size_order(batch_size)
    if parsed_order is None:
        return batch_size
    effective_order: int = grain_sizes[effective_grain][0]
    if parsed_order >= effective_order:
        return batch_size
    return grain_sizes[effective_grain][1]


def _timestamp_batch_size_order(batch_size: str) -> int | None:
    if batch_size.endswith("y") and not batch_size.endswith("dy"):
        return 5
    if batch_size.endswith("mo"):
        return 4
    if batch_size.endswith("d"):
        return 3
    if batch_size.endswith("h"):
        return 2
    if batch_size.endswith("m"):
        return 1
    if batch_size.endswith("s"):
        return 0
    return None


def _add_timestamp_interval(
    *,
    current: datetime,
    years: int,
    months: int,
    days: int,
    hours: int,
    minutes: int,
    seconds: int,
) -> datetime:
    result: datetime = current
    if years:
        result = result.replace(year=result.year + years)
    if months:
        total_month: int = (result.month - 1) + months
        year: int = result.year + (total_month // 12)
        month: int = (total_month % 12) + 1
        result = result.replace(year=year, month=month)
    if days or hours or minutes or seconds:
        result = result + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    return result
