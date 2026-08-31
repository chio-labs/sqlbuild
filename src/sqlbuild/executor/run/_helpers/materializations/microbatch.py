"""Microbatch incremental execution lifecycle."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import uuid4

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.relations.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.fingerprints.main.compute_query_hash import compute_query_hash
from sqlbuild.compiler.planner.main.execution.cursor_bound_display import cursor_bound_display
from sqlbuild.compiler.planner.main.execution.effective_microbatch_batch_size import (
    resolve_effective_microbatch_batch_size,
)
from sqlbuild.compiler.planner.main.execution.inclusive_cursor_end import inclusive_cursor_end
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    CursorInputRelation,
    Duration,
    ModelPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    CursorGrain,
    CursorType,
    IncrementalStrategy,
    OnSchemaChange,
    PlanReason,
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
from sqlbuild.executor.run._helpers.materializations.full_refresh import (
    promote_full_refresh_rebuild,
    relation_exists,
    resolve_full_refresh_relations,
)
from sqlbuild.executor.run._helpers.materializations.incremental import (
    _apply_schema_change,
    _execute_dml,
)
from sqlbuild.executor.run._helpers.reuse.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run._helpers.validation.cursor_bounds import (
    build_runtime_cursor_spec,
    has_model_backed_cursor_inputs,
    resolve_effective_timestamp_grain,
    resolve_runtime_cursor_bounds,
    substitute_cursor_sentinels,
)
from sqlbuild.executor.run._helpers.validation.type_enforcement import enforce_types_staged
from sqlbuild.executor.run.models import (
    BatchWindow,
    FinalAuditRun,
    FullRefreshRelations,
    MicrobatchAccountingInterval,
    MicrobatchLifecycleState,
    MicrobatchPhaseOutcome,
    MicrobatchSchemaPhaseOutcome,
    MicrobatchTargets,
    ModelExecutionResult,
    ModelMaterializationContext,
    PostHookPhaseOutcome,
)
from sqlbuild.executor.run.types import ExecutionPhase, MicrobatchBatchRunner
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.microbatches.classes.direct_store import (
    DirectMicrobatchEventStore,
    direct_microbatch_scope,
)
from sqlbuild.microbatches.constants import (
    DIRECT_MICROBATCH_SCOPE_KIND,
    MICROBATCH_GENERATION_WILDCARD,
    MICROBATCH_REPLAY_GENERATION_PREFIX,
)
from sqlbuild.microbatches.main.latest_replay_requirement import (
    latest_active_replay_requirement,
)
from sqlbuild.microbatches.main.project_coverage import project_microbatch_coverage
from sqlbuild.microbatches.main.project_replay import project_replay_requirement
from sqlbuild.microbatches.models import (
    MicrobatchCoverageProjection,
    MicrobatchEvent,
    MicrobatchInterval,
    MicrobatchScope,
    ProjectedMicrobatchInterval,
    ReplayRequirementProjection,
)
from sqlbuild.microbatches.types import (
    MicrobatchCompletionType,
    MicrobatchEventStore,
    MicrobatchFingerprintStatus,
    MicrobatchRecordType,
    MicrobatchRunType,
    ReplayRequirementState,
    UnaccountedPartitionPolicy,
)
from sqlbuild.spec.contracts.types import TableType

_DEFAULT_ON_SCHEMA_CHANGE: OnSchemaChange = OnSchemaChange.APPEND_NEW_COLUMNS
_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")
_EMPTY_INTEGER_CURSOR_BOUND: str = "0"
_EMPTY_TIMESTAMP_CURSOR_BOUND: str = "1970-01-01T00:00:00"
_UNACCOUNTED_COUNT_CHUNK_SIZE: int = 100
_FIRST_MONTH: int = 1
_FINAL_MONTH: int = 12


@dataclass(frozen=True)
class _MicrobatchPlan:
    """Planned batch windows or the early-exit result when none can run."""

    batches: tuple[BatchWindow, ...] = ()
    effective_batch_size: str | None = None
    resolved_range: CursorBounds | None = None
    early_exit: ModelExecutionResult | None = None


@dataclass(frozen=True)
class _MicrobatchHistoryContext:
    store: MicrobatchEventStore
    scope: MicrobatchScope
    history: tuple[MicrobatchEvent, ...]
    run_type: MicrobatchRunType
    run_start: str
    run_end: str
    batch_size: str
    replay_requirement_id: str | None = None
    origin_run_id: str | None = None
    origin_run_started_at: datetime | None = None
    execution_run_started_at: datetime | None = None
    recovery_intervals: frozenset[tuple[str, str]] = frozenset()
    known_missing_intervals: tuple[MicrobatchInterval, ...] = ()
    unaccounted_intervals: tuple[MicrobatchInterval, ...] = ()
    synthetic_intervals: tuple[MicrobatchInterval, ...] = ()
    accounting_intervals: tuple[MicrobatchAccountingInterval, ...] = ()
    replay_requirement_state: ReplayRequirementState | None = None
    replay_unknown_fingerprint_count: int = 0
    contiguous_frontier: str | None = None
    unaccounted_partition_policy: str = "synthesize"
    required_model_version_hash: str | None = None
    concurrent_enabled: bool = False
    batch_concurrency: int = 1
    global_concurrency: int = 1
    recovery_origins: dict[tuple[str, str], _RecoveryOrigin] = field(default_factory=dict)


@dataclass(frozen=True)
class _RecoveryOrigin:
    origin_run_id: str
    origin_run_started_at: datetime | None
    run_start: str
    run_end: str
    run_type: MicrobatchRunType
    replay_requirement_id: str | None


def execute_microbatch_entry(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
    is_full_refresh: bool = False,
    on_progress: Callable[[str], None] | None = None,
) -> ModelExecutionResult:
    """Execute one microbatch incremental model through batched delta/DML."""

    targets: MicrobatchTargets = _resolve_microbatch_targets(context=context)
    full_refresh_relations: FullRefreshRelations | None = None
    if is_full_refresh:
        full_refresh_relations = resolve_full_refresh_relations(
            adapter=context.adapter,
            database=context.entry.destination.database,
            schema=context.entry.destination.schema,
            target_name=context.entry.destination.name,
        )
        targets = replace(
            targets,
            target_table=full_refresh_relations.rebuild_name,
            target_qualified=full_refresh_relations.rebuild_qualified,
        )
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
    history_read: (
        tuple[
            MicrobatchEventStore,
            MicrobatchScope,
            tuple[MicrobatchEvent, ...],
            tuple[MicrobatchEvent, ...],
        ]
        | ModelExecutionResult
    ) = _read_microbatch_history(context=context, state=state, is_full_refresh=is_full_refresh)
    if isinstance(history_read, ModelExecutionResult):
        return history_read
    event_store, event_scope, event_history, model_history = history_read
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
    history_context: _MicrobatchHistoryContext | ModelExecutionResult = _prepare_microbatch_history(
        context=context,
        state=state,
        batch_plan=batch_plan,
        store=event_store,
        scope=event_scope,
        history=event_history,
        transition_history=model_history,
    )
    if isinstance(history_context, ModelExecutionResult):
        return history_context
    if full_refresh_relations is not None:
        preparation_failure: ModelExecutionResult | None = _prepare_full_refresh_rebuild(
            context=context,
            state=state,
            relations=full_refresh_relations,
        )
        if preparation_failure is not None:
            return preparation_failure
    if history_context.run_type == MicrobatchRunType.REPLAY_ON_CHANGE:
        replay_batches: tuple[BatchWindow, ...] = compute_batch_windows(
            start=history_context.run_start,
            end=history_context.run_end,
            batch_size=history_context.batch_size,
            cursor_type=context.entry.cursor_type or "",
        )
        batch_plan = replace(
            batch_plan,
            batches=replay_batches,
            resolved_range=CursorBounds(
                start=history_context.run_start, end=history_context.run_end
            ),
        )
    reconciliation: (
        tuple[_MicrobatchHistoryContext, tuple[BatchWindow, ...]] | ModelExecutionResult
    ) = _reconcile_microbatch_history(
        context=context,
        state=state,
        targets=targets,
        history=history_context,
        normal_batches=batch_plan.batches,
        is_full_refresh=is_full_refresh,
    )
    if isinstance(reconciliation, ModelExecutionResult):
        return reconciliation
    history_context, reconciled_batches = reconciliation
    batch_plan = replace(batch_plan, batches=reconciled_batches)
    reconciliation_warnings: list[str] = []
    if history_context.synthetic_intervals:
        reconciliation_warnings.append(
            f"microbatch history did not account for "
            f"{len(history_context.synthetic_intervals)} intervals in '{context.entry.name}'; "
            "SQLBuild accepted synthetic physical coverage, but their model fingerprints "
            "are unknown"
        )
    if (
        history_context.replay_requirement_id is not None
        and history_context.replay_unknown_fingerprint_count
    ):
        reconciliation_warnings.append(
            f"replay-on-change for '{context.entry.name}' has "
            f"{history_context.replay_unknown_fingerprint_count} intervals with "
            "synthetic coverage and unknown fingerprints"
        )
    elif (
        history_context.replay_unknown_fingerprint_count and not history_context.synthetic_intervals
    ):
        reconciliation_warnings.append(
            f"microbatch history for '{context.entry.name}' retains "
            f"{history_context.replay_unknown_fingerprint_count} intervals with "
            "synthetic coverage and unknown fingerprints"
        )
    state = replace(state, warnings=[*state.warnings, *reconciliation_warnings])
    if not batch_plan.batches:
        state = replace(state, warnings=[*state.warnings, "no batches to process"])
    if (
        on_progress is not None
        and context.entry.microbatch_range is None
        and batch_plan.resolved_range is not None
        and batch_plan.effective_batch_size is not None
    ):
        on_progress(
            _format_resolved_microbatch_progress(
                bounds=batch_plan.resolved_range,
                batch_count=len(batch_plan.batches),
                batch_size=batch_plan.effective_batch_size,
                cursor_type=context.entry.cursor_type,
                cursor_grain=context.entry.cursor_grain,
            )
        )
    batch_outcome: MicrobatchPhaseOutcome = _execute_microbatch_batches(
        context=context,
        declared_columns=declared_columns,
        is_full_refresh=is_full_refresh,
        batches=batch_plan.batches,
        targets=targets,
        state=state,
        history_context=history_context,
        on_progress=on_progress,
    )
    state = batch_outcome.state
    history_context = _refresh_microbatch_result_history(
        context=context,
        history=history_context,
        batches=batch_plan.batches,
        physical_target_name=targets.target_table,
    )
    if batch_outcome.failure is not None:
        return replace(
            batch_outcome.failure,
            batch_count=batch_outcome.completed_batches,
            batch_size=batch_plan.effective_batch_size,
            rows_affected=batch_outcome.rows_affected,
            **_microbatch_result_fields(history=history_context, succeeded=False),
        )
    final_audit_run: FinalAuditRun = run_final_scope_audits(
        context=context,
        relation_override=(
            None if full_refresh_relations is None else full_refresh_relations.rebuild_qualified
        ),
    )
    state.audit_results.extend(final_audit_run.results)
    if final_audit_run.has_error:
        return replace(
            build_failed_result(
                entry=context.entry,
                phase=ExecutionPhase.AUDIT,
                error=(
                    f"final audit for '{context.entry.name}' failed before full-refresh promotion "
                    if full_refresh_relations is not None
                    else f"final audit for '{context.entry.name}' failed after target update "
                )
                + ("with severity level: error"),
                promoted_relation=targets.target_qualified,
                warnings=state.warnings,
                audit_results=state.audit_results,
                statement_recorder=state.statement_recorder,
            ),
            **_microbatch_result_fields(history=history_context, succeeded=True),
        )
    if full_refresh_relations is not None:
        promotion_failure: ModelExecutionResult | None = _promote_microbatch_full_refresh(
            context=context,
            state=state,
            relations=full_refresh_relations,
        )
        if promotion_failure is not None:
            return promotion_failure
    post_hook_outcome: PostHookPhaseOutcome = run_post_hook_phase(
        context=context,
        warnings=state.warnings,
        audit_results=state.audit_results,
        hook_results=state.hook_results,
        statement_recorder=state.statement_recorder,
        promoted_relation=targets.target_qualified,
    )
    if post_hook_outcome.failure is not None:
        return replace(
            post_hook_outcome.failure,
            **_microbatch_result_fields(history=history_context, succeeded=True),
        )
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
    resolved_range: CursorBounds | None = batch_plan.resolved_range
    return ModelExecutionResult(
        model_name=context.entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=targets.target_qualified,
        batch_count=batch_outcome.completed_batches,
        batch_size=batch_plan.effective_batch_size,
        rows_affected=batch_outcome.rows_affected,
        cursor_range_start=None if resolved_range is None else resolved_range.start,
        cursor_range_end=None if resolved_range is None else resolved_range.end,
        cursor_type=context.entry.cursor_type,
        cursor_grain=context.entry.cursor_grain,
        audit_results=tuple(state.audit_results),
        warning_messages=tuple(state.warnings),
        lifecycle_events=state.statement_recorder.snapshot(),
        hook_results=tuple(state.hook_results),
        **_microbatch_result_fields(history=history_context, succeeded=True),
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
    history_context: _MicrobatchHistoryContext,
    on_progress: Callable[[str], None] | None = None,
) -> MicrobatchPhaseOutcome:
    if context.microbatch_batch_runner is not None and not is_full_refresh and len(batches) > 1:
        return _execute_microbatch_batches_concurrently(
            context=context,
            declared_columns=declared_columns,
            batches=batches,
            targets=targets,
            state=state,
            history_context=history_context,
            on_progress=on_progress,
        )
    schema_checked: bool = False
    completed_batches: int = 0
    total_rows: int = 0
    row_count_known: bool = False
    total_batches: int = len(batches)
    batch: BatchWindow
    for batch in batches:
        lease_failure: ModelExecutionResult | None = _microbatch_lease_failure(
            context=context,
            state=state,
            batch=batch,
            boundary="batch staging",
        )
        if lease_failure is not None:
            return MicrobatchPhaseOutcome(
                state=state,
                failure=lease_failure,
                completed_batches=completed_batches,
            )
        batch_targets: MicrobatchTargets = _targets_for_batch(
            context=context, targets=targets, batch=batch
        )
        batch_start_time: float = time.monotonic()
        window_text: str = f"{batch.start}..{batch.end}"
        display_window: str = _format_batch_window_for_display(batch=batch, entry=context.entry)
        if on_progress is not None:
            on_progress(f"batch {completed_batches + 1}/{total_batches} {display_window}")
        stage_failure: ModelExecutionResult | None = _stage_microbatch_delta(
            context=context,
            batch=batch,
            window_text=window_text,
            targets=batch_targets,
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
            targets=batch_targets,
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
            targets=batch_targets,
            state=state,
        )
        if type_failure is not None:
            return MicrobatchPhaseOutcome(
                state=state, failure=type_failure, completed_batches=completed_batches
            )
        audit_outcome: MicrobatchPhaseOutcome = _run_microbatch_delta_audits(
            context=context,
            batch=batch,
            targets=batch_targets,
            state=state,
        )
        state = audit_outcome.state
        if audit_outcome.failure is not None:
            return replace(audit_outcome, completed_batches=completed_batches)
        lease_failure = _microbatch_lease_failure(
            context=context,
            state=state,
            batch=batch,
            boundary="target DML",
        )
        if lease_failure is not None:
            return MicrobatchPhaseOutcome(
                state=state,
                failure=lease_failure,
                completed_batches=completed_batches,
            )
        dml_result: ModelExecutionResult | int | None = _apply_microbatch_dml(
            context=context,
            batch=batch,
            completed_batches=completed_batches,
            is_full_refresh=is_full_refresh,
            window_text=window_text,
            targets=batch_targets,
            state=state,
        )
        if isinstance(dml_result, ModelExecutionResult):
            return MicrobatchPhaseOutcome(
                state=state,
                failure=dml_result,
                completed_batches=completed_batches,
                rows_affected=_reported_rows_affected(
                    total_rows=total_rows,
                    row_count_known=row_count_known,
                ),
            )
        if isinstance(dml_result, int):
            total_rows += dml_result
            row_count_known = True
        lease_failure = _microbatch_lease_failure(
            context=context,
            state=state,
            batch=batch,
            boundary="completion publication",
        )
        if lease_failure is not None:
            return MicrobatchPhaseOutcome(
                state=state,
                failure=lease_failure,
                completed_batches=completed_batches,
                rows_affected=_reported_rows_affected(
                    total_rows=total_rows,
                    row_count_known=row_count_known,
                ),
            )
        completion_failure: ModelExecutionResult | None = _record_microbatch_completion(
            context=context,
            batch=batch,
            is_full_refresh=is_full_refresh,
            rows_affected=dml_result if isinstance(dml_result, int) else None,
            history=history_context,
            state=state,
            targets=batch_targets,
        )
        if completion_failure is not None:
            return MicrobatchPhaseOutcome(
                state=state,
                failure=completion_failure,
                completed_batches=completed_batches,
                rows_affected=_reported_rows_affected(
                    total_rows=total_rows, row_count_known=row_count_known
                ),
            )
        _complete_microbatch_batch(
            context=context,
            window_text=window_text,
            targets=batch_targets,
            state=state,
        )
        completed_batches += 1
        if on_progress is not None:
            batch_elapsed: float = time.monotonic() - batch_start_time
            on_progress(
                f"batch {completed_batches}/{total_batches} {display_window} {batch_elapsed:.1f}s"
            )
    return MicrobatchPhaseOutcome(
        state=state,
        completed_batches=completed_batches,
        rows_affected=_reported_rows_affected(
            total_rows=total_rows,
            row_count_known=row_count_known,
        ),
    )


def _microbatch_lease_failure(
    *,
    context: ModelMaterializationContext,
    state: MicrobatchLifecycleState,
    batch: BatchWindow,
    boundary: str,
) -> ModelExecutionResult | None:
    if context.microbatch_lease_check is None:
        return None
    try:
        context.microbatch_lease_check()
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.MICROBATCH_STATE,
            error=(
                f"microbatch lease check failed before {boundary} for batch {batch.index}: {exc}"
            ),
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    return None


def _execute_microbatch_batches_concurrently(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
    batches: tuple[BatchWindow, ...],
    targets: MicrobatchTargets,
    state: MicrobatchLifecycleState,
    history_context: _MicrobatchHistoryContext,
    on_progress: Callable[[str], None] | None,
) -> MicrobatchPhaseOutcome:
    recovery_batches: tuple[BatchWindow, ...] = tuple(
        batch for batch in batches if (batch.start, batch.end) in history_context.recovery_intervals
    )
    ordinary_batches: tuple[BatchWindow, ...] = tuple(
        batch
        for batch in batches
        if (batch.start, batch.end) not in history_context.recovery_intervals
    )
    completed_batches: int = 0
    total_rows: int = 0
    row_count_known: bool = False
    for phase_batches in (recovery_batches, ordinary_batches):
        if not phase_batches:
            continue
        phase_outcome: MicrobatchPhaseOutcome = _execute_concurrent_microbatch_phase(
            context=context,
            declared_columns=declared_columns,
            batches=phase_batches,
            targets=targets,
            aggregate_state=state,
            history_context=history_context,
            on_progress=on_progress,
        )
        state = phase_outcome.state
        completed_batches += phase_outcome.completed_batches
        if phase_outcome.rows_affected is not None:
            total_rows += phase_outcome.rows_affected
            row_count_known = True
        if phase_outcome.failure is not None:
            return MicrobatchPhaseOutcome(
                state=state,
                failure=phase_outcome.failure,
                completed_batches=completed_batches,
                rows_affected=_reported_rows_affected(
                    total_rows=total_rows, row_count_known=row_count_known
                ),
            )
    return MicrobatchPhaseOutcome(
        state=state,
        completed_batches=completed_batches,
        rows_affected=_reported_rows_affected(
            total_rows=total_rows, row_count_known=row_count_known
        ),
    )


def _execute_concurrent_microbatch_phase(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
    batches: tuple[BatchWindow, ...],
    targets: MicrobatchTargets,
    aggregate_state: MicrobatchLifecycleState,
    history_context: _MicrobatchHistoryContext,
    on_progress: Callable[[str], None] | None,
) -> MicrobatchPhaseOutcome:
    first: BatchWindow = batches[0]
    serial_context: ModelMaterializationContext = replace(context, microbatch_batch_runner=None)
    first_outcome: MicrobatchPhaseOutcome = _execute_microbatch_batches(
        context=serial_context,
        declared_columns=declared_columns,
        is_full_refresh=False,
        batches=(first,),
        targets=targets,
        state=aggregate_state,
        history_context=history_context,
        on_progress=on_progress,
    )
    if first_outcome.failure is not None or len(batches) == 1:
        return first_outcome

    def execute(*, batch: BatchWindow, connection: Any) -> MicrobatchPhaseOutcome:
        worker_state: MicrobatchLifecycleState = MicrobatchLifecycleState(
            warnings=[],
            audit_results=[],
            hook_results=[],
            statement_recorder=StatementRecorder(),
        )
        worker_store: MicrobatchEventStore = (
            context.microbatch_event_store_resolver(connection)
            if context.microbatch_event_store_resolver is not None
            else history_context.store
        )
        return _execute_microbatch_batches(
            context=replace(
                context,
                connection=connection,
                microbatch_batch_runner=None,
                microbatch_event_store=worker_store,
            ),
            declared_columns=declared_columns,
            is_full_refresh=False,
            batches=(batch,),
            targets=targets,
            state=worker_state,
            history_context=replace(history_context, store=worker_store),
            on_progress=on_progress,
        )

    runner: MicrobatchBatchRunner | None = context.microbatch_batch_runner
    if runner is None:
        return first_outcome
    outcomes: tuple[MicrobatchPhaseOutcome, ...] = runner(
        batches[1:],
        context.entry.batch_concurrency,
        lambda batch, connection: execute(batch=batch, connection=connection),
    )
    completed_batches: int = first_outcome.completed_batches
    total_rows: int = first_outcome.rows_affected or 0
    row_count_known: bool = first_outcome.rows_affected is not None
    failure: ModelExecutionResult | None = None
    for outcome in outcomes:
        aggregate_state = _merge_microbatch_states(target=aggregate_state, source=outcome.state)
        completed_batches += outcome.completed_batches
        if outcome.rows_affected is not None:
            total_rows += outcome.rows_affected
            row_count_known = True
        if failure is None and outcome.failure is not None:
            failure = outcome.failure
    return MicrobatchPhaseOutcome(
        state=aggregate_state,
        failure=failure,
        completed_batches=completed_batches,
        rows_affected=_reported_rows_affected(
            total_rows=total_rows, row_count_known=row_count_known
        ),
    )


def _merge_microbatch_states(
    *, target: MicrobatchLifecycleState, source: MicrobatchLifecycleState
) -> MicrobatchLifecycleState:
    recorder: StatementRecorder = StatementRecorder()
    recorder.events.extend(target.statement_recorder.snapshot())
    recorder.events.extend(source.statement_recorder.snapshot())
    return MicrobatchLifecycleState(
        warnings=[*target.warnings, *source.warnings],
        audit_results=[*target.audit_results, *source.audit_results],
        hook_results=[*target.hook_results, *source.hook_results],
        statement_recorder=recorder,
    )


def _targets_for_batch(
    *, context: ModelMaterializationContext, targets: MicrobatchTargets, batch: BatchWindow
) -> MicrobatchTargets:
    if context.entry.batch_concurrency <= 1:
        return targets
    identity: str = hashlib.sha256(
        f"{context.run_id}:{batch.index}:{batch.start}:{batch.end}".encode()
    ).hexdigest()[:12]
    suffix: str = f"__delta_{identity}"
    max_length: int = context.adapter.maximum_identifier_length()
    target_prefix: str = targets.target_table[: max(1, max_length - len(suffix))]
    delta_table: str = f"{target_prefix}{suffix}"
    return replace(
        targets,
        delta_table=delta_table,
        delta_qualified=resolve_qualified_name_parts(
            adapter=context.adapter,
            database=targets.target_database,
            schema=targets.target_schema,
            name=delta_table,
        ),
    )


def _read_microbatch_history(
    *,
    context: ModelMaterializationContext,
    state: MicrobatchLifecycleState,
    is_full_refresh: bool,
) -> (
    tuple[
        MicrobatchEventStore,
        MicrobatchScope,
        tuple[MicrobatchEvent, ...],
        tuple[MicrobatchEvent, ...],
    ]
    | ModelExecutionResult
):
    store: MicrobatchEventStore = context.microbatch_event_store or DirectMicrobatchEventStore(
        adapter=context.adapter, connection=context.connection
    )
    scope: MicrobatchScope = context.microbatch_scope or direct_microbatch_scope(
        adapter=context.adapter, connection=context.connection, entry=context.entry
    )
    try:
        all_history: tuple[MicrobatchEvent, ...] = store.read_model_history(scope)
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.MICROBATCH_STATE,
            error=f"failed to read microbatch history: {exc}",
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    if is_full_refresh and scope.scope_kind == DIRECT_MICROBATCH_SCOPE_KIND:
        if _microbatch_run_type(context=context) == MicrobatchRunType.REPLAY_ON_CHANGE:
            replay_generation: str = (
                MICROBATCH_REPLAY_GENERATION_PREFIX + _expected_model_version_hash(context=context)
            )
            scope = replace(scope, physical_generation_id=replay_generation)
            return (
                store,
                scope,
                tuple(
                    event
                    for event in all_history
                    if event.scope.physical_generation_id == replay_generation
                ),
                all_history,
            )
        scope = replace(scope, physical_generation_id=context.run_id)
        return store, scope, (), all_history
    if scope.physical_generation_id != MICROBATCH_GENERATION_WILDCARD:
        return (
            store,
            scope,
            tuple(
                event
                for event in all_history
                if event.scope.physical_generation_id == scope.physical_generation_id
            ),
            all_history,
        )
    if not all_history:
        scope = replace(scope, physical_generation_id=scope.scope_key)
        return store, scope, (), all_history
    latest_generation: str = max(
        all_history, key=lambda event: (event.created_at, event.event_id)
    ).scope.physical_generation_id
    scope = replace(scope, physical_generation_id=latest_generation)
    history: tuple[MicrobatchEvent, ...] = tuple(
        event for event in all_history if event.scope.physical_generation_id == latest_generation
    )
    return store, scope, history, all_history


def _prepare_microbatch_history(
    *,
    context: ModelMaterializationContext,
    state: MicrobatchLifecycleState,
    batch_plan: _MicrobatchPlan,
    store: MicrobatchEventStore,
    scope: MicrobatchScope,
    history: tuple[MicrobatchEvent, ...],
    transition_history: tuple[MicrobatchEvent, ...],
) -> _MicrobatchHistoryContext | ModelExecutionResult:
    resolved_range: CursorBounds | None = batch_plan.resolved_range
    batch_size: str | None = batch_plan.effective_batch_size
    if resolved_range is None or batch_size is None:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.MICROBATCH_STATE,
            error="microbatch history requires resolved bounds and batch size",
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    run_type: MicrobatchRunType = _microbatch_run_type(context=context)
    expected_version_hash: str = _expected_model_version_hash(context=context)
    execution_run_started_at: datetime = datetime.now(tz=UTC)
    requirement: MicrobatchEvent | None = None
    if run_type == MicrobatchRunType.REPLAY_ON_CHANGE:
        requirement = latest_active_replay_requirement(
            events=tuple(
                event
                for event in history
                if event.previous_model_version_hash == context.entry.previous_version_hash
            ),
            current_model_version_hash=expected_version_hash,
        )
        if requirement is not None and not _replay_requirement_still_active(
            requirement=requirement,
            history=transition_history,
            cursor_type=context.entry.cursor_type or "",
        ):
            requirement = None
        if requirement is None:
            requirement_id: str = uuid4().hex
            requirement = MicrobatchEvent(
                event_id=uuid4().hex,
                record_type=MicrobatchRecordType.REPLAY_REQUIREMENT,
                scope=scope,
                origin_run_id=context.run_id,
                execution_run_id=context.run_id,
                run_type=run_type,
                run_start=resolved_range.start,
                run_end=resolved_range.end,
                batch_size=batch_size,
                cursor_column=context.entry.cursor_column or "",
                cursor_type=context.entry.cursor_type or "",
                cursor_grain=context.entry.cursor_grain,
                model_version_hash=expected_version_hash,
                definition_hash=compute_query_hash(context.entry.fingerprint_query_sql),
                fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
                replay_requirement_id=requirement_id,
                required_model_version_hash=expected_version_hash,
                previous_model_version_hash=context.entry.previous_version_hash,
                replay_policy=(
                    context.entry.backfill.duration
                    if context.entry.backfill.action == BackfillAction.BOUNDED
                    else context.entry.backfill.action.value
                ),
                origin_run_started_at=execution_run_started_at,
                execution_run_started_at=execution_run_started_at,
            )
            try:
                store = _append_microbatch_event(store=store, event=requirement)
            except Exception as exc:
                return build_failed_result(
                    entry=context.entry,
                    phase=ExecutionPhase.MICROBATCH_STATE,
                    error=f"failed to append replay requirement: {exc}",
                    warnings=state.warnings,
                    audit_results=state.audit_results,
                    statement_recorder=state.statement_recorder,
                )
    effective_history: tuple[MicrobatchEvent, ...] = (
        (*history, requirement)
        if requirement is not None and requirement not in history
        else history
    )
    return _MicrobatchHistoryContext(
        store=store,
        scope=scope,
        history=effective_history,
        run_type=run_type,
        run_start=requirement.run_start if requirement is not None else resolved_range.start,
        run_end=requirement.run_end if requirement is not None else resolved_range.end,
        batch_size=requirement.batch_size if requirement is not None else batch_size,
        replay_requirement_id=(
            requirement.replay_requirement_id if requirement is not None else None
        ),
        origin_run_id=requirement.origin_run_id if requirement is not None else context.run_id,
        origin_run_started_at=(
            requirement.origin_run_started_at
            if requirement is not None
            else execution_run_started_at
        ),
        execution_run_started_at=execution_run_started_at,
        replay_requirement_state=(
            ReplayRequirementState.INCOMPLETE if requirement is not None else None
        ),
        unaccounted_partition_policy=context.microbatch_unaccounted_partition_policy,
        required_model_version_hash=(
            requirement.required_model_version_hash if requirement is not None else None
        ),
        concurrent_enabled=context.microbatch_batch_runner is not None,
        batch_concurrency=context.entry.batch_concurrency,
        global_concurrency=context.microbatch_global_concurrency,
    )


def _replay_requirement_still_active(
    *, requirement: MicrobatchEvent, history: tuple[MicrobatchEvent, ...], cursor_type: str
) -> bool:
    requirement_order: tuple[float, str] = (
        requirement.created_at.timestamp(),
        requirement.event_id,
    )
    if any(
        event.record_type
        in {
            MicrobatchRecordType.PARTITION_COMPLETION,
            MicrobatchRecordType.REPLAY_REQUIREMENT,
        }
        and (
            event.record_type == MicrobatchRecordType.REPLAY_REQUIREMENT
            or event.model_version_hash
            not in {
                None,
                requirement.required_model_version_hash,
            }
        )
        and (event.created_at.timestamp(), event.event_id) > requirement_order
        for event in history
    ):
        return False
    expected_intervals: tuple[MicrobatchInterval, ...] = tuple(
        MicrobatchInterval(start=batch.start, end=batch.end)
        for batch in compute_batch_windows(
            start=requirement.run_start,
            end=requirement.run_end,
            batch_size=requirement.batch_size,
            cursor_type=cursor_type,
        )
    )
    projection: ReplayRequirementProjection = project_replay_requirement(
        requirement=requirement,
        current_model_version_hash=requirement.required_model_version_hash or "",
        expected_intervals=expected_intervals,
        coverage=project_microbatch_coverage(
            events=history,
            expected_intervals=expected_intervals,
            cursor_type=cursor_type,
        ),
        cursor_type=cursor_type,
    )
    return projection.state == ReplayRequirementState.INCOMPLETE


def _record_microbatch_completion(
    *,
    context: ModelMaterializationContext,
    batch: BatchWindow,
    is_full_refresh: bool,
    rows_affected: int | None,
    history: _MicrobatchHistoryContext,
    state: MicrobatchLifecycleState,
    targets: MicrobatchTargets,
) -> ModelExecutionResult | None:
    now: datetime = datetime.now(tz=UTC)
    recovery_origin: _RecoveryOrigin | None = history.recovery_origins.get((batch.start, batch.end))
    completion_scope: MicrobatchScope = _current_completion_scope(
        context=context,
        scope=history.scope,
        physical_target_name=(
            targets.target_table if is_full_refresh else context.entry.destination.name
        ),
    )
    event: MicrobatchEvent = MicrobatchEvent(
        event_id=uuid4().hex,
        record_type=MicrobatchRecordType.PARTITION_COMPLETION,
        scope=completion_scope,
        origin_run_id=(
            recovery_origin.origin_run_id
            if recovery_origin is not None
            else history.origin_run_id or context.run_id
        ),
        execution_run_id=context.run_id,
        run_type=(recovery_origin.run_type if recovery_origin is not None else history.run_type),
        completion_type=(
            MicrobatchCompletionType.RECOVERY
            if (batch.start, batch.end) in history.recovery_intervals
            else MicrobatchCompletionType.INITIAL
        ),
        run_start=(recovery_origin.run_start if recovery_origin is not None else history.run_start),
        run_end=(recovery_origin.run_end if recovery_origin is not None else history.run_end),
        partition_start=batch.start,
        partition_end=batch.end,
        batch_size=history.batch_size,
        cursor_column=context.entry.cursor_column or "",
        cursor_type=context.entry.cursor_type or "",
        cursor_grain=context.entry.cursor_grain,
        model_version_hash=_expected_model_version_hash(context=context),
        definition_hash=compute_query_hash(context.entry.fingerprint_query_sql),
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
        replay_requirement_id=(
            recovery_origin.replay_requirement_id
            if recovery_origin is not None
            else history.replay_requirement_id
        ),
        rows_affected=rows_affected,
        completed_at=now,
        origin_run_started_at=(
            recovery_origin.origin_run_started_at
            if recovery_origin is not None
            else history.origin_run_started_at
        ),
        execution_run_started_at=history.execution_run_started_at,
    )
    try:
        _append_microbatch_event(store=history.store, event=event)
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.MICROBATCH_STATE,
            error=f"batch {batch.index}: target DML succeeded but completion write failed: {exc}",
            staging_relation=targets.delta_qualified,
            promoted_relation=targets.target_qualified,
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    return None


def _microbatch_run_type(*, context: ModelMaterializationContext) -> MicrobatchRunType:
    entry: ModelPlanEntry = context.entry
    if entry.start_cursor_override is not None or entry.end_cursor_override is not None:
        return MicrobatchRunType.BACKFILL
    if (
        entry.backfill.action in {BackfillAction.BOUNDED, BackfillAction.FULL}
        and entry.previous_version_hash is not None
        and _expected_model_version_hash(context=context) != entry.previous_version_hash
    ):
        return MicrobatchRunType.REPLAY_ON_CHANGE
    return MicrobatchRunType.NORMAL


def _expected_model_version_hash(*, context: ModelMaterializationContext) -> str:
    return (
        context.microbatch_model_version_hash
        or context.entry.fingerprint_version_hash
        or compute_query_hash(context.entry.fingerprint_query_sql)
    )


def _current_completion_scope(
    *,
    context: ModelMaterializationContext,
    scope: MicrobatchScope,
    physical_target_name: str | None = None,
) -> MicrobatchScope:
    if (
        scope.physical_generation_id.startswith(MICROBATCH_REPLAY_GENERATION_PREFIX)
        or context.entry.reason == PlanReason.FULL_REFRESH
    ):
        return scope
    generation: str | None = context.adapter.physical_relation_generation(
        connection=context.connection,
        database=context.entry.destination.database,
        schema=context.entry.destination.schema,
        name=physical_target_name or context.entry.destination.name,
    )
    if generation is None:
        return scope
    if scope.scope_kind == DIRECT_MICROBATCH_SCOPE_KIND:
        return replace(scope, physical_generation_id=generation)
    generation_hash: str = hashlib.sha256(generation.encode()).hexdigest()
    if scope.physical_generation_id.rpartition(":")[2] == generation_hash:
        return scope
    return replace(
        scope,
        physical_generation_id=f"{scope.physical_generation_id}:{generation_hash}",
    )


def _reconcile_microbatch_history(
    *,
    context: ModelMaterializationContext,
    state: MicrobatchLifecycleState,
    targets: MicrobatchTargets,
    history: _MicrobatchHistoryContext,
    normal_batches: tuple[BatchWindow, ...],
    is_full_refresh: bool,
) -> tuple[_MicrobatchHistoryContext, tuple[BatchWindow, ...]] | ModelExecutionResult:
    if is_full_refresh:
        return history, normal_batches
    cursor_type: str = context.entry.cursor_type or ""
    if cursor_type not in {CursorType.TIMESTAMP, CursorType.INTEGER}:
        return history, normal_batches
    envelope: CursorBounds | None | ModelExecutionResult = _physical_cursor_envelope(
        context=context, state=state, targets=targets
    )
    if isinstance(envelope, ModelExecutionResult):
        return envelope
    expected_intervals: tuple[MicrobatchInterval, ...] = _accounting_intervals(
        context=context, history=history, envelope=envelope
    )
    coverage: MicrobatchCoverageProjection = project_microbatch_coverage(
        events=history.history,
        expected_intervals=expected_intervals,
        cursor_type=cursor_type,
    )
    policy_result: (
        tuple[tuple[MicrobatchInterval, ...], tuple[MicrobatchInterval, ...]] | ModelExecutionResult
    ) = _apply_unaccounted_policy(
        context=context,
        state=state,
        targets=targets,
        history=history,
        intervals=coverage.unaccounted,
    )
    if isinstance(policy_result, ModelExecutionResult):
        return policy_result
    policy_recovery, synthetic_intervals = policy_result
    (
        replay_recovery,
        replay_requirement_state,
        replay_unknown_fingerprint_count,
    ) = _replay_recovery_intervals(
        context=context,
        history=history,
        synthetic_intervals=synthetic_intervals,
    )
    recovery: tuple[MicrobatchInterval, ...] = _deduplicate_intervals(
        (*coverage.known_missing, *policy_recovery, *replay_recovery)
    )
    recovery_keys: frozenset[tuple[str, str]] = frozenset(
        (interval.start, interval.end) for interval in recovery
    )
    recovery_batches: tuple[BatchWindow, ...] = tuple(
        BatchWindow(start=interval.start, end=interval.end, index=index)
        for index, interval in enumerate(recovery)
    )
    ordinary_batches: tuple[BatchWindow, ...] = (
        ()
        if history.run_type == MicrobatchRunType.REPLAY_ON_CHANGE
        else tuple(
            batch for batch in normal_batches if (batch.start, batch.end) not in recovery_keys
        )
    )
    all_batches: tuple[BatchWindow, ...] = tuple(
        replace(batch, index=index)
        for index, batch in enumerate((*recovery_batches, *ordinary_batches))
    )
    accounting_intervals: tuple[MicrobatchAccountingInterval, ...] = (
        _build_microbatch_accounting_intervals(
            coverage=coverage.intervals,
            known_missing=coverage.known_missing,
            unaccounted=coverage.unaccounted,
            synthetic=synthetic_intervals,
            recovery=recovery,
        )
    )
    recovery_origins: dict[tuple[str, str], _RecoveryOrigin] = _known_gap_origins(
        events=history.history,
        known_missing=coverage.known_missing,
        cursor_type=cursor_type,
    )
    return (
        replace(
            history,
            recovery_intervals=recovery_keys,
            known_missing_intervals=coverage.known_missing,
            unaccounted_intervals=coverage.unaccounted,
            synthetic_intervals=synthetic_intervals,
            accounting_intervals=accounting_intervals,
            replay_requirement_state=replay_requirement_state,
            replay_unknown_fingerprint_count=max(
                replay_unknown_fingerprint_count,
                len(coverage.unknown_fingerprints) + len(synthetic_intervals),
            ),
            contiguous_frontier=coverage.contiguous_frontier,
            recovery_origins=recovery_origins,
        ),
        all_batches,
    )


def _accounting_intervals(
    *,
    context: ModelMaterializationContext,
    history: _MicrobatchHistoryContext,
    envelope: CursorBounds | None,
) -> tuple[MicrobatchInterval, ...]:
    cursor_type: str = context.entry.cursor_type or ""
    continuity_events: tuple[MicrobatchEvent, ...] = tuple(
        event
        for event in history.history
        if event.run_type != MicrobatchRunType.BACKFILL
        and event.partition_start is not None
        and event.partition_end is not None
    )
    starts: list[str] = [
        event.partition_start for event in continuity_events if event.partition_start is not None
    ]
    ends: list[str] = [
        event.partition_end for event in history.history if event.partition_end is not None
    ]
    if envelope is not None:
        if not starts:
            starts.append(envelope.start)
        ends.append(envelope.end)
    if context.entry.cursor_start is not None and not starts:
        starts.append(context.entry.cursor_start)
    if not starts or not ends:
        return ()
    floor: str = _cursor_bound(values=starts, cursor_type=cursor_type, maximum=False)
    frontier: str = _cursor_bound(values=ends, cursor_type=cursor_type, maximum=True)
    return tuple(
        MicrobatchInterval(start=batch.start, end=batch.end)
        for batch in compute_batch_windows(
            start=floor,
            end=frontier,
            batch_size=history.batch_size,
            cursor_type=cursor_type,
        )
    )


def _apply_unaccounted_policy(
    *,
    context: ModelMaterializationContext,
    state: MicrobatchLifecycleState,
    targets: MicrobatchTargets,
    history: _MicrobatchHistoryContext,
    intervals: tuple[MicrobatchInterval, ...],
) -> tuple[tuple[MicrobatchInterval, ...], tuple[MicrobatchInterval, ...]] | ModelExecutionResult:
    if not intervals:
        return (), ()
    policy: UnaccountedPartitionPolicy = UnaccountedPartitionPolicy(
        context.microbatch_unaccounted_partition_policy
    )
    if policy == UnaccountedPartitionPolicy.RECOVER_ALL:
        return intervals, ()
    if policy == UnaccountedPartitionPolicy.SYNTHESIZE:
        failure: ModelExecutionResult | None = _append_synthetic_completions(
            context=context,
            state=state,
            history=history,
            intervals=intervals,
            policy=policy,
            row_counts=None,
        )
        return failure if failure is not None else ((), intervals)
    counts: dict[tuple[str, str], int] | ModelExecutionResult = _count_unaccounted_intervals(
        context=context,
        state=state,
        targets=targets,
        intervals=intervals,
    )
    if isinstance(counts, ModelExecutionResult):
        return counts
    empty: tuple[MicrobatchInterval, ...] = tuple(
        interval for interval in intervals if counts[(interval.start, interval.end)] == 0
    )
    non_empty: tuple[MicrobatchInterval, ...] = tuple(
        interval for interval in intervals if counts[(interval.start, interval.end)] > 0
    )
    failure = _append_synthetic_completions(
        context=context,
        state=state,
        history=history,
        intervals=non_empty,
        policy=policy,
        row_counts=counts,
    )
    return failure if failure is not None else (empty, non_empty)


def _replay_recovery_intervals(
    *,
    context: ModelMaterializationContext,
    history: _MicrobatchHistoryContext,
    synthetic_intervals: tuple[MicrobatchInterval, ...],
) -> tuple[tuple[MicrobatchInterval, ...], ReplayRequirementState | None, int]:
    if history.replay_requirement_id is None:
        return (), None, 0
    requirement: MicrobatchEvent | None = next(
        (
            event
            for event in history.history
            if event.record_type == MicrobatchRecordType.REPLAY_REQUIREMENT
            and event.replay_requirement_id == history.replay_requirement_id
        ),
        None,
    )
    if requirement is None:
        return (), None, 0
    replay_intervals: tuple[MicrobatchInterval, ...] = tuple(
        MicrobatchInterval(start=batch.start, end=batch.end)
        for batch in compute_batch_windows(
            start=requirement.run_start,
            end=requirement.run_end,
            batch_size=requirement.batch_size,
            cursor_type=context.entry.cursor_type or "",
        )
    )
    projection: ReplayRequirementProjection = project_replay_requirement(
        requirement=requirement,
        current_model_version_hash=_expected_model_version_hash(context=context),
        expected_intervals=replay_intervals,
        coverage=project_microbatch_coverage(
            events=history.history,
            expected_intervals=replay_intervals,
            cursor_type=context.entry.cursor_type or "",
        ),
        cursor_type=context.entry.cursor_type or "",
    )
    synthetic_keys: frozenset[tuple[str, str]] = frozenset(
        (interval.start, interval.end) for interval in synthetic_intervals
    )
    if projection.state == ReplayRequirementState.SUPERSEDED:
        return (), projection.state, len(projection.unknown_fingerprints)
    return (
        tuple(
            interval
            for interval in projection.missing
            if (interval.start, interval.end) not in synthetic_keys
        ),
        projection.state,
        len(projection.unknown_fingerprints) + len(synthetic_intervals),
    )


def _physical_cursor_envelope(
    *,
    context: ModelMaterializationContext,
    state: MicrobatchLifecycleState,
    targets: MicrobatchTargets,
) -> CursorBounds | None | ModelExecutionResult:
    if not context.adapter.relation_exists(
        connection=context.connection,
        database=targets.target_database,
        schema=targets.target_schema,
        name=targets.target_table,
    ):
        return None
    cursor_column: str | None = context.entry.cursor_column
    if cursor_column is None:
        return None
    quoted_cursor: str = context.adapter.render_identifier(cursor_column)
    try:
        cursor: Any = context.adapter.execute(
            connection=context.connection,
            sql=(
                f"SELECT MIN({quoted_cursor}), MAX({quoted_cursor}) FROM {targets.target_qualified}"
            ),
        )
        row: Any = cursor.fetchone()
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.MICROBATCH_STATE,
            error=f"failed to inspect target cursor envelope: {exc}",
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    if row is None or row[0] is None or row[1] is None:
        return None
    return _canonical_destination_envelope(
        raw_min=row[0],
        raw_max=row[1],
        cursor_type=context.entry.cursor_type,
        cursor_grain=context.entry.cursor_grain,
    )


def _canonical_destination_envelope(
    *, raw_min: object, raw_max: object, cursor_type: str | None, cursor_grain: str | None
) -> CursorBounds:
    if cursor_type == CursorType.INTEGER:
        return CursorBounds(
            start=str(int(Decimal(str(raw_min)))),
            end=str(int(Decimal(str(raw_max))) + 1),
        )
    if not isinstance(raw_min, datetime | date) or not isinstance(raw_max, datetime | date):
        raise ExecutorInputError("timestamp cursor envelope returned non-temporal bounds")
    grain: str = cursor_grain or CursorGrain.SECOND
    start: datetime | date = _floor_temporal_bound(value=raw_min, grain=grain)
    end_floor: datetime | date = _floor_temporal_bound(value=raw_max, grain=grain)
    end: datetime | date = _increment_temporal_bound(value=end_floor, grain=grain)
    return CursorBounds(start=start.isoformat(), end=end.isoformat())


def _floor_temporal_bound(*, value: datetime | date, grain: str) -> datetime | date:
    if isinstance(value, datetime):
        if grain == CursorGrain.SECOND:
            return value.replace(microsecond=0)
        if grain == CursorGrain.MINUTE:
            return value.replace(second=0, microsecond=0)
        if grain == CursorGrain.HOUR:
            return value.replace(minute=0, second=0, microsecond=0)
        if grain == CursorGrain.DAY:
            return value.replace(hour=0, minute=0, second=0, microsecond=0)
        if grain == CursorGrain.MONTH:
            return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if grain == CursorGrain.YEAR:
            return value.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if grain == CursorGrain.MONTH:
        return value.replace(day=1)
    if grain == CursorGrain.YEAR:
        return value.replace(month=1, day=1)
    return value


def _increment_temporal_bound(*, value: datetime | date, grain: str) -> datetime | date:
    if grain == CursorGrain.SECOND:
        return value + timedelta(seconds=1)
    if grain == CursorGrain.MINUTE:
        return value + timedelta(minutes=1)
    if grain == CursorGrain.HOUR:
        return value + timedelta(hours=1)
    if grain == CursorGrain.DAY:
        return value + timedelta(days=1)
    if grain == CursorGrain.MONTH:
        return value.replace(
            year=value.year + (1 if value.month == _FINAL_MONTH else 0),
            month=_FIRST_MONTH if value.month == _FINAL_MONTH else value.month + 1,
            day=1,
        )
    if grain == CursorGrain.YEAR:
        return value.replace(year=value.year + 1, month=1, day=1)
    return value


def _append_synthetic_completions(
    *,
    context: ModelMaterializationContext,
    state: MicrobatchLifecycleState,
    history: _MicrobatchHistoryContext,
    intervals: tuple[MicrobatchInterval, ...],
    policy: UnaccountedPartitionPolicy,
    row_counts: dict[tuple[str, str], int] | None,
) -> ModelExecutionResult | None:
    if not intervals:
        return None
    now: datetime = datetime.now(tz=UTC)
    try:
        for interval in intervals:
            _append_microbatch_event(
                store=history.store,
                event=MicrobatchEvent(
                    event_id=uuid4().hex,
                    record_type=MicrobatchRecordType.SYNTHETIC_COMPLETION,
                    scope=history.scope,
                    origin_run_id=context.run_id,
                    origin_run_started_at=history.execution_run_started_at,
                    execution_run_id=context.run_id,
                    execution_run_started_at=history.execution_run_started_at,
                    run_type=history.run_type,
                    completion_type=MicrobatchCompletionType.RECOVERY,
                    run_start=history.run_start,
                    run_end=history.run_end,
                    partition_start=interval.start,
                    partition_end=interval.end,
                    batch_size=history.batch_size,
                    cursor_column=context.entry.cursor_column or "",
                    cursor_type=context.entry.cursor_type or "",
                    cursor_grain=context.entry.cursor_grain,
                    model_version_hash=None,
                    definition_hash=None,
                    fingerprint_status=MicrobatchFingerprintStatus.UNKNOWN,
                    coverage_source="synthetic",
                    observed_row_count=(
                        None if row_counts is None else row_counts[(interval.start, interval.end)]
                    ),
                    observed_at=now,
                    synthetic_reason="completion_history_missing",
                    unaccounted_policy=policy,
                ),
            )
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.MICROBATCH_STATE,
            error=f"failed to append synthetic microbatch coverage: {exc}",
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    return None


def _count_unaccounted_intervals(
    *,
    context: ModelMaterializationContext,
    state: MicrobatchLifecycleState,
    targets: MicrobatchTargets,
    intervals: tuple[MicrobatchInterval, ...],
) -> dict[tuple[str, str], int] | ModelExecutionResult:
    cursor_column: str = context.adapter.render_identifier(context.entry.cursor_column or "")
    counts: dict[tuple[str, str], int] = {}
    chunk_start: int
    for chunk_start in range(0, len(intervals), _UNACCOUNTED_COUNT_CHUNK_SIZE):
        chunk: tuple[MicrobatchInterval, ...] = intervals[
            chunk_start : chunk_start + _UNACCOUNTED_COUNT_CHUNK_SIZE
        ]
        expressions: list[str] = []
        for index, interval in enumerate(chunk):
            start_literal: str = context.adapter.render_cursor_bound_literal(
                value=interval.start, cursor_type=context.entry.cursor_type
            )
            end_literal: str = context.adapter.render_cursor_bound_literal(
                value=interval.end, cursor_type=context.entry.cursor_type
            )
            expressions.append(
                f"SUM(CASE WHEN {cursor_column} >= {start_literal} AND "
                f"{cursor_column} < {end_literal} THEN 1 ELSE 0 END) "
                f"AS __sqb_count_{index}"
            )
        try:
            cursor: Any = context.adapter.execute(
                connection=context.connection,
                sql=f"SELECT {', '.join(expressions)} FROM {targets.target_qualified}",
            )
            row: Any = cursor.fetchone()
        except Exception as exc:
            return build_failed_result(
                entry=context.entry,
                phase=ExecutionPhase.MICROBATCH_STATE,
                error=f"failed to count unaccounted microbatch intervals: {exc}",
                warnings=state.warnings,
                audit_results=state.audit_results,
                statement_recorder=state.statement_recorder,
            )
        counts.update(
            {
                (interval.start, interval.end): int(row[index] or 0)
                for index, interval in enumerate(chunk)
            }
        )
    return counts


def _deduplicate_intervals(
    intervals: tuple[MicrobatchInterval, ...],
) -> tuple[MicrobatchInterval, ...]:
    return tuple({(interval.start, interval.end): interval for interval in intervals}.values())


def _build_microbatch_accounting_intervals(
    *,
    coverage: tuple[ProjectedMicrobatchInterval, ...],
    known_missing: tuple[MicrobatchInterval, ...],
    unaccounted: tuple[MicrobatchInterval, ...],
    synthetic: tuple[MicrobatchInterval, ...],
    recovery: tuple[MicrobatchInterval, ...],
) -> tuple[MicrobatchAccountingInterval, ...]:
    results: list[MicrobatchAccountingInterval] = [
        MicrobatchAccountingInterval(
            partition_start=interval.start,
            partition_end=interval.end,
            accounting_status=(
                "synthetic"
                if interval.record_type == MicrobatchRecordType.SYNTHETIC_COMPLETION
                else "ordinary_completion"
            ),
            fingerprint_status=interval.fingerprint_status.value,
            model_version_hash=interval.model_version_hash,
            completion_type=(
                None if interval.completion_type is None else interval.completion_type.value
            ),
            event_id=interval.event_id,
        )
        for interval in coverage
    ]
    recovery_keys: frozenset[tuple[str, str]] = frozenset(
        (interval.start, interval.end) for interval in recovery
    )
    synthetic_keys: frozenset[tuple[str, str]] = frozenset(
        (interval.start, interval.end) for interval in synthetic
    )
    for interval in known_missing:
        results.append(
            MicrobatchAccountingInterval(
                partition_start=interval.start,
                partition_end=interval.end,
                accounting_status="recovery_pending",
                fingerprint_status=MicrobatchFingerprintStatus.UNKNOWN.value,
            )
        )
    for interval in unaccounted:
        key: tuple[str, str] = (interval.start, interval.end)
        status: str = "unaccounted"
        if key in synthetic_keys:
            status = "synthetic"
        elif key in recovery_keys:
            status = "recovery_pending"
        results.append(
            MicrobatchAccountingInterval(
                partition_start=interval.start,
                partition_end=interval.end,
                accounting_status=status,
                fingerprint_status=MicrobatchFingerprintStatus.UNKNOWN.value,
            )
        )
    return tuple(results)


def _known_gap_origins(
    *,
    events: tuple[MicrobatchEvent, ...],
    known_missing: tuple[MicrobatchInterval, ...],
    cursor_type: str,
) -> dict[tuple[str, str], _RecoveryOrigin]:
    origins: dict[tuple[str, str], _RecoveryOrigin] = {}
    for interval in known_missing:
        candidates: tuple[MicrobatchEvent, ...] = tuple(
            event
            for event in events
            if event.record_type == MicrobatchRecordType.PARTITION_COMPLETION
            and event.partition_start is not None
            and _cursor_lte(
                left=interval.end,
                right=event.partition_start,
                cursor_type=cursor_type,
            )
            and _cursor_lte(left=event.run_start, right=interval.start, cursor_type=cursor_type)
            and _cursor_lte(left=interval.end, right=event.run_end, cursor_type=cursor_type)
        )
        if not candidates:
            continue
        witness: MicrobatchEvent = min(
            candidates, key=lambda event: (event.created_at, event.event_id)
        )
        origins[(interval.start, interval.end)] = _RecoveryOrigin(
            origin_run_id=witness.origin_run_id,
            origin_run_started_at=witness.origin_run_started_at,
            run_start=witness.run_start,
            run_end=witness.run_end,
            run_type=witness.run_type,
            replay_requirement_id=witness.replay_requirement_id,
        )
    return origins


def _cursor_lte(*, left: str, right: str, cursor_type: str) -> bool:
    if cursor_type == CursorType.TIMESTAMP:
        return datetime.fromisoformat(left) <= datetime.fromisoformat(right)
    return Decimal(left) <= Decimal(right)


def _microbatch_result_fields(
    *, history: _MicrobatchHistoryContext, succeeded: bool
) -> dict[str, Any]:
    replay_state: ReplayRequirementState | None = history.replay_requirement_state
    if succeeded and history.run_type == MicrobatchRunType.REPLAY_ON_CHANGE:
        if (
            replay_state == ReplayRequirementState.COMPLETE_WITH_UNKNOWN_FINGERPRINTS
            or history.synthetic_intervals
        ):
            replay_state = ReplayRequirementState.COMPLETE_WITH_UNKNOWN_FINGERPRINTS
        else:
            replay_state = ReplayRequirementState.VERIFIED_COMPLETE
    return {
        "microbatch_run_type": history.run_type.value,
        "microbatch_recovery_batch_count": len(history.recovery_intervals),
        "microbatch_known_gap_count": len(history.known_missing_intervals),
        "microbatch_unaccounted_interval_count": len(history.unaccounted_intervals),
        "microbatch_synthetic_completion_count": len(history.synthetic_intervals),
        "microbatch_unknown_fingerprint_count": history.replay_unknown_fingerprint_count,
        "microbatch_contiguous_frontier": history.contiguous_frontier,
        "microbatch_unaccounted_partition_policy": history.unaccounted_partition_policy,
        "microbatch_replay_requirement_id": history.replay_requirement_id,
        "microbatch_required_model_version_hash": history.required_model_version_hash,
        "microbatch_physical_generation_id": history.scope.physical_generation_id,
        "microbatch_concurrent_enabled": history.concurrent_enabled,
        "microbatch_batch_concurrency": history.batch_concurrency,
        "microbatch_global_concurrency": history.global_concurrency,
        "microbatch_replay_requirement_state": (
            None if replay_state is None else replay_state.value
        ),
        "microbatch_accounting_intervals": history.accounting_intervals,
    }


def _refresh_microbatch_result_history(
    *,
    context: ModelMaterializationContext,
    history: _MicrobatchHistoryContext,
    batches: tuple[BatchWindow, ...],
    physical_target_name: str,
) -> _MicrobatchHistoryContext:
    if not batches:
        return history
    expected: tuple[MicrobatchInterval, ...] = tuple(
        MicrobatchInterval(start=batch.start, end=batch.end) for batch in batches
    )
    current_scope: MicrobatchScope = _current_completion_scope(
        context=context, scope=history.scope, physical_target_name=physical_target_name
    )
    try:
        events: tuple[MicrobatchEvent, ...] = history.store.read_scope_history(current_scope)
    except Exception:
        return history
    coverage: MicrobatchCoverageProjection = project_microbatch_coverage(
        events=events,
        expected_intervals=expected,
        cursor_type=context.entry.cursor_type or "",
    )
    synthetic: tuple[MicrobatchInterval, ...] = tuple(
        MicrobatchInterval(start=interval.start, end=interval.end)
        for interval in coverage.intervals
        if interval.record_type == MicrobatchRecordType.SYNTHETIC_COMPLETION
    )
    replay_state: ReplayRequirementState | None = history.replay_requirement_state
    if history.replay_requirement_id is not None:
        requirement: MicrobatchEvent | None = next(
            (
                event
                for event in events
                if event.record_type == MicrobatchRecordType.REPLAY_REQUIREMENT
                and event.replay_requirement_id == history.replay_requirement_id
            ),
            None,
        )
        if requirement is not None:
            replay_state = project_replay_requirement(
                requirement=requirement,
                current_model_version_hash=_expected_model_version_hash(context=context),
                expected_intervals=expected,
                coverage=coverage,
                cursor_type=context.entry.cursor_type or "",
            ).state
    return replace(
        history,
        scope=current_scope,
        history=events,
        synthetic_intervals=synthetic,
        replay_requirement_state=replay_state,
        contiguous_frontier=coverage.contiguous_frontier,
        accounting_intervals=_build_microbatch_accounting_intervals(
            coverage=coverage.intervals,
            known_missing=coverage.known_missing,
            unaccounted=coverage.unaccounted,
            synthetic=synthetic,
            recovery=(),
        ),
    )


def _cursor_bound(*, values: list[str], cursor_type: str, maximum: bool) -> str:
    if cursor_type == CursorType.TIMESTAMP:
        return (
            max(values, key=datetime.fromisoformat)
            if maximum
            else min(values, key=datetime.fromisoformat)
        )
    return (
        max(values, key=lambda value: Decimal(value))
        if maximum
        else min(values, key=lambda value: Decimal(value))
    )


def _cursor_result_string(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)


def _reported_rows_affected(*, total_rows: int, row_count_known: bool) -> int | None:
    """Preserve a known zero row count while keeping unavailable counts as None."""

    return total_rows if row_count_known else None


def _append_microbatch_event(
    *, store: MicrobatchEventStore, event: MicrobatchEvent
) -> MicrobatchEventStore:
    store.write(event)
    return store


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
                table_type=TableType.TRANSIENT,
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
            batch_rows: int | None = _count_microbatch_delta_rows(context=context, targets=targets)
            if is_full_refresh and completed_batches == 0:
                context.adapter.create_table_as(
                    connection=context.connection,
                    destination=targets.target_qualified,
                    sql=f"SELECT * FROM {targets.delta_qualified}",
                    config={"table_type": context.entry.table_type},
                    statement_recorder=state.statement_recorder,
                )
            else:
                reported_rows: int | None = _execute_dml(
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
                if reported_rows is not None:
                    batch_rows = reported_rows
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


def _count_microbatch_delta_rows(
    *, context: ModelMaterializationContext, targets: MicrobatchTargets
) -> int | None:
    """Return the staged row count used for completion provenance."""

    cursor: Any = context.adapter.execute(
        connection=context.connection,
        sql=f"SELECT COUNT(*) FROM {targets.delta_qualified}",
    )
    row: Any = cursor.fetchone()
    return None if row is None or row[0] is None else int(row[0])


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


def _prepare_full_refresh_rebuild(
    *,
    context: ModelMaterializationContext,
    state: MicrobatchLifecycleState,
    relations: FullRefreshRelations,
) -> ModelExecutionResult | None:
    """Inspect or initialize the deterministic full-refresh rebuild relation."""

    try:
        live_exists: bool = relation_exists(
            adapter=context.adapter,
            connection=context.connection,
            database=context.entry.destination.database,
            schema=context.entry.destination.schema,
            name=relations.target_name,
        )
        rebuild_exists: bool = relation_exists(
            adapter=context.adapter,
            connection=context.connection,
            database=context.entry.destination.database,
            schema=context.entry.destination.schema,
            name=relations.rebuild_name,
        )
        if not live_exists and rebuild_exists:
            context.adapter.rename(
                connection=context.connection,
                origin=relations.rebuild_qualified,
                destination=relations.target_qualified,
                statement_recorder=state.statement_recorder,
            )
        elif not live_exists and context.entry.reason == PlanReason.FULL_REFRESH:
            raise ExecutorInputError(
                "full-refresh reconciliation found neither the live target nor its rebuild "
                f"relation for '{context.entry.name}'"
            )
        elif rebuild_exists:
            context.adapter.drop(
                connection=context.connection,
                destination=relations.rebuild_qualified,
                if_exists=True,
                statement_recorder=state.statement_recorder,
            )
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.STAGING,
            error=str(exc),
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
        )
    return None


def _promote_microbatch_full_refresh(
    *,
    context: ModelMaterializationContext,
    state: MicrobatchLifecycleState,
    relations: FullRefreshRelations,
) -> ModelExecutionResult | None:
    """Promote a complete rebuild while retaining the outgoing generation."""

    try:
        live_exists: bool = relation_exists(
            adapter=context.adapter,
            connection=context.connection,
            database=context.entry.destination.database,
            schema=context.entry.destination.schema,
            name=relations.target_name,
        )
        promote_full_refresh_rebuild(
            adapter=context.adapter,
            connection=context.connection,
            relations=relations,
            target_exists=live_exists,
            statement_recorder=state.statement_recorder,
        )
    except Exception as exc:
        return build_failed_result(
            entry=context.entry,
            phase=ExecutionPhase.DML,
            error=f"failed to promote full-refresh rebuild: {exc}",
            staging_relation=relations.rebuild_qualified,
            promoted_relation=relations.target_qualified,
            warnings=state.warnings,
            audit_results=state.audit_results,
            statement_recorder=state.statement_recorder,
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
    runtime_discovery: bool = runtime_owned_cursor_bounds or is_full_refresh
    microbatch_range: CursorBounds | None = entry.microbatch_range
    if runtime_discovery:
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
                spec=build_runtime_cursor_spec(
                    entry=entry,
                    read_destination_cursor=not is_full_refresh,
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
    if microbatch_range is None:
        empty_bound: str = _empty_microbatch_bound(entry=entry)
        microbatch_range = CursorBounds(start=empty_bound, end=empty_bound)

    effective_batch_size: str = batch_size
    if runtime_discovery:
        effective_timestamp_grain: str | None = resolve_effective_timestamp_grain(
            cursor_type=cursor_type,
            downstream_grain=entry.cursor_grain,
            cursor_input_relations=entry.cursor_input_relations,
        )
        if effective_timestamp_grain is not None:
            effective_batch_size = resolve_effective_microbatch_batch_size(
                batch_size=batch_size,
                effective_grain=effective_timestamp_grain,
            )

    batches: tuple[BatchWindow, ...] = (
        (BatchWindow(start=microbatch_range.start, end=microbatch_range.end, index=0),)
        if is_full_refresh and microbatch_range.start == microbatch_range.end
        else compute_batch_windows(
            start=microbatch_range.start,
            end=microbatch_range.end,
            batch_size=effective_batch_size,
            cursor_type=cursor_type,
        )
    )

    return _MicrobatchPlan(
        batches=batches,
        effective_batch_size=effective_batch_size,
        resolved_range=microbatch_range,
    )


def _empty_microbatch_bound(*, entry: ModelPlanEntry) -> str:
    if entry.cursor_start is not None:
        return entry.cursor_start
    if entry.cursor_type == CursorType.INTEGER:
        return _EMPTY_INTEGER_CURSOR_BOUND
    return _EMPTY_TIMESTAMP_CURSOR_BOUND


def _format_resolved_microbatch_progress(
    *,
    bounds: CursorBounds,
    batch_count: int,
    batch_size: str,
    cursor_type: str | None,
    cursor_grain: str | None,
) -> str:
    """Format the concrete runtime-owned range before its first batch starts."""

    start: str = cursor_bound_display(
        value=bounds.start,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
    )
    end: str = inclusive_cursor_end(
        end=bounds.end,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
    )
    batch_noun: str = "batch" if batch_count == 1 else "batches"
    return f"resolved runtime range {start} -> {end} ({batch_count} {batch_noun} x {batch_size})"


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


def _format_batch_window_for_display(*, batch: BatchWindow, entry: ModelPlanEntry) -> str:
    """Render a batch window for progress output, collapsing whole-day bounds to dates."""

    start: str = cursor_bound_display(
        value=batch.start,
        cursor_type=entry.cursor_type,
        cursor_grain=entry.cursor_grain,
    )
    end: str = cursor_bound_display(
        value=batch.end,
        cursor_type=entry.cursor_type,
        cursor_grain=entry.cursor_grain,
    )
    return f"{start}..{end}"


def _substitute_sentinels(
    *,
    sql: str,
    batch_start: str,
    batch_end: str,
) -> str:
    """Replace microbatch cursor sentinels with concrete batch bounds."""

    return substitute_cursor_sentinels(
        sql=sql,
        bounds=CursorBounds(start=batch_start, end=batch_end),
    )


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
    discovery_sql: str = "SELECT MIN(_min), MIN(_max) FROM (" + " UNION ALL ".join(parts) + ")"
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

    duration: Duration | None = Duration.parse(batch_size)
    if duration is None:
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
        batch_end: datetime = min(duration.add_to(current), end_dt)
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
