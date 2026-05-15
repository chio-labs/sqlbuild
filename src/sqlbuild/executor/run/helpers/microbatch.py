"""Microbatch incremental execution lifecycle."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationTarget
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
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
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.cursor_bounds import (
    has_model_backed_cursor_inputs,
    resolve_effective_timestamp_grain,
    resolve_runtime_cursor_bounds,
)
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks, render_hooks
from sqlbuild.executor.run.helpers.incremental import (
    _apply_schema_change,
    _execute_dml,
)
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.helpers.type_enforcement import enforce_types_staged
from sqlbuild.executor.run.models import BatchWindow, ModelExecutionResult
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.shared.helpers.diagnostics_logging import diagnostics_context, log_debug_event
from sqlbuild.shared.helpers.naming import (
    resolve_qualified_name_parts,
    resolve_target_qualified_name,
)
from sqlbuild.spec.models.source import SourceEntry

_DEFAULT_ON_SCHEMA_CHANGE: OnSchemaChange = OnSchemaChange.APPEND_NEW_COLUMNS
_DURATION_PATTERN_STR: str = (
    r"^(?:(\d+)y)?(?:(\d+)mo)?(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"
)
_DEBUG_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")


def execute_microbatch_entry(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    declared_columns: tuple[ColumnInfo, ...],
    run_id: str,
    query_change_tracking: bool,
    is_full_refresh: bool = False,
) -> ModelExecutionResult:
    """Execute one microbatch incremental model through batched delta/DML."""

    target_database: str | None = entry.target.database
    target_schema: str | None = entry.target.schema
    target_table: str = entry.target.name
    target_qualified: str = resolve_target_qualified_name(adapter=adapter, target=entry.target)
    delta_table: str = f"{target_table}__delta"
    delta_qualified: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=target_database,
        schema=target_schema,
        name=delta_table,
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []
    statement_recorder: StatementRecorder = StatementRecorder()
    runtime_owned_cursor_bounds: bool = has_model_backed_cursor_inputs(entry.cursor_input_relations)

    try:
        statement_recorder.record_many(render_hooks(hooks=entry.pre_hook, phase_label="pre_hook"))
        with diagnostics_context(sqlbuild_phase="pre_hook", sqlbuild_action_name="run"):
            execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.pre_hook,
                phase_label="pre_hook",
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.PRE_HOOK,
            error=str(exc),
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    microbatch_range: CursorBounds | None = entry.microbatch_range
    if runtime_owned_cursor_bounds:
        if entry.cursor_column is None:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error="runtime-owned cursor resolution requires cursor_column",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )
        try:
            microbatch_range = resolve_runtime_cursor_bounds(
                adapter=adapter,
                connection=connection,
                target_relation=target_qualified,
                cursor_column=entry.cursor_column,
                cursor_type=entry.cursor_type,
                cursor_grain=entry.cursor_grain,
                cursor_start=entry.cursor_start,
                cursor_input_relations=entry.cursor_input_relations,
            )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"failed to discover runtime microbatch cursor range: {exc}",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
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
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"failed to discover microbatch cursor range: {exc}",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )
        if microbatch_range is None:
            return ModelExecutionResult(
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

    if microbatch_range is None:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.STAGING,
            error="microbatch_range is not available and model is not full refresh",
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    batch_size: str | None = entry.batch_size
    cursor_type: str | None = entry.cursor_type
    if batch_size is None or cursor_type is None:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.STAGING,
            error="microbatch requires batch_size and cursor_type",
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
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
        return ModelExecutionResult(
            model_name=entry.name,
            status=ExecutionStatus.SUCCESS,
            promoted_relation=target_qualified,
            audit_results=tuple(audit_results),
            warning_messages=(*tuple(warnings), "no batches to process"),
            lifecycle_events=statement_recorder.snapshot(),
        )

    if is_full_refresh:
        try:
            with diagnostics_context(sqlbuild_phase="cleanup", sqlbuild_action_name="drop_target"):
                adapter.drop(
                    connection,
                    target=target_qualified,
                    if_exists=True,
                    statement_recorder=statement_recorder,
                )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"failed to drop target for full-refresh microbatch: {exc}",
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )

    schema_checked: bool = False
    completed_batches: int = 0
    batch: BatchWindow
    for batch in batches:
        window_text: str = f"{batch.start}..{batch.end}"
        log_debug_event(
            _DEBUG_LOGGER,
            "",
            sqlbuild_subject="model",
            sqlbuild_name=entry.name,
            sqlbuild_event="batch_start",
            sqlbuild_phase="batch",
            sqlbuild_window=window_text,
        )
        batch_sql: str = _substitute_sentinels(
            sql=entry.resolved_sql,
            batch_start=batch.start,
            batch_end=batch.end,
        )

        try:
            with diagnostics_context(
                sqlbuild_phase="materialize",
                sqlbuild_action_name="create_delta",
                sqlbuild_window=window_text,
            ):
                adapter.drop(
                    connection,
                    target=delta_qualified,
                    if_exists=True,
                    statement_recorder=statement_recorder,
                )
                adapter.create_table_as(
                    connection,
                    target=delta_qualified,
                    sql=batch_sql,
                    statement_recorder=statement_recorder,
                )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"batch {batch.index}: {exc}",
                staging_relation=delta_qualified,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )

        if not schema_checked and not is_full_refresh:
            try:
                with diagnostics_context(
                    sqlbuild_phase="schema_change",
                    sqlbuild_action_name="inspect",
                    sqlbuild_window=window_text,
                ):
                    delta_columns: tuple[ColumnInfo, ...] = adapter.get_columns(
                        connection,
                        database=target_database,
                        schema=target_schema,
                        name=delta_table,
                    )
                    target_columns: tuple[ColumnInfo, ...] = adapter.get_columns(
                        connection,
                        database=target_database,
                        schema=target_schema,
                        name=target_table,
                    )
                    _apply_schema_change(
                        adapter=adapter,
                        connection=connection,
                        target_qualified=target_qualified,
                        target_columns=target_columns,
                        delta_columns=delta_columns,
                        on_schema_change=entry.on_schema_change or _DEFAULT_ON_SCHEMA_CHANGE,
                        warnings=warnings,
                        statement_recorder=statement_recorder,
                    )
            except Exception as exc:
                return build_failed_result(
                    entry=entry,
                    phase=ExecutionPhase.SCHEMA_CHANGE,
                    error=str(exc),
                    staging_relation=delta_qualified,
                    warnings=warnings,
                    audit_results=audit_results,
                    statement_recorder=statement_recorder,
                )
            schema_checked = True

        if entry.type_enforcement and declared_columns:
            try:
                with diagnostics_context(
                    sqlbuild_phase="type_enforcement",
                    sqlbuild_action_name="rebuild_delta",
                    sqlbuild_window=window_text,
                ):
                    enforce_types_staged(
                        adapter=adapter,
                        connection=connection,
                        staging_qualified=delta_qualified,
                        staging_database=target_database,
                        staging_schema=target_schema,
                        staging_table=delta_table,
                        declared_columns=declared_columns,
                        statement_recorder=statement_recorder,
                    )
            except Exception as exc:
                return build_failed_result(
                    entry=entry,
                    phase=ExecutionPhase.TYPE_ENFORCEMENT,
                    error=f"batch {batch.index}: {exc}",
                    staging_relation=delta_qualified,
                    warnings=warnings,
                    audit_results=audit_results,
                    statement_recorder=statement_recorder,
                )

        delta_overrides: dict[str, str] = {entry.name: delta_qualified}
        delta_audit_error: bool = False
        audit: AuditPlanEntry
        for audit in model_audits:
            if audit.effective_run_scope == AuditRunScope.DELTA_AND_FINAL:
                result: AuditExecutionResult = execute_audit(
                    audit=audit,
                    adapter=adapter,
                    connection=connection,
                    model_targets=model_targets,
                    seed_targets=seed_targets,
                    source_map=source_map,
                    relation_overrides=delta_overrides,
                    run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
                )
                audit_results.append(result)
                if result.outcome == AuditOutcome.ERROR:
                    delta_audit_error = True

        if delta_audit_error:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.AUDIT,
                error=(
                    f"batch {batch.index}: delta audit for '{entry.name}' failed before "
                    "target update with severity level: error"
                ),
                staging_relation=delta_qualified,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )

        try:
            with diagnostics_context(
                sqlbuild_phase="dml",
                sqlbuild_action_name="apply",
                sqlbuild_window=window_text,
            ):
                target_columns_for_dml: tuple[ColumnInfo, ...] = (
                    adapter.get_columns(
                        connection,
                        database=target_database,
                        schema=target_schema,
                        name=target_table,
                    )
                    if not is_full_refresh or completed_batches > 0
                    else ()
                )
                delta_columns_for_dml: tuple[ColumnInfo, ...] = adapter.get_columns(
                    connection,
                    database=target_database,
                    schema=target_schema,
                    name=delta_table,
                )
                _validate_cursor_output_columns(entry=entry, delta_columns=delta_columns_for_dml)
                if is_full_refresh and completed_batches == 0:
                    adapter.create_table_as(
                        connection,
                        target=target_qualified,
                        sql=f"SELECT * FROM {delta_qualified}",
                        statement_recorder=statement_recorder,
                    )
                else:
                    _execute_dml(
                        adapter=adapter,
                        connection=connection,
                        target_qualified=target_qualified,
                        delta_qualified=delta_qualified,
                        target_columns=target_columns_for_dml,
                        delta_columns=delta_columns_for_dml,
                        entry=entry,
                        cursor_start=batch.start,
                        cursor_end=batch.end,
                        statement_recorder=statement_recorder,
                    )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.DML,
                error=f"batch {batch.index}: {exc}",
                staging_relation=delta_qualified,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )

        with diagnostics_context(
            sqlbuild_phase="cleanup",
            sqlbuild_action_name="drop_delta",
            sqlbuild_window=window_text,
        ):
            adapter.drop(
                connection,
                target=delta_qualified,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        log_debug_event(
            _DEBUG_LOGGER,
            "",
            sqlbuild_subject="model",
            sqlbuild_name=entry.name,
            sqlbuild_event="batch_complete",
            sqlbuild_phase="batch",
            sqlbuild_window=window_text,
            sqlbuild_status="ok",
        )
        completed_batches += 1

    final_audit_error: bool = False
    for audit in model_audits:
        result = execute_audit(
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
            final_audit_error = True

    if final_audit_error:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"final audit for '{entry.name}' failed after target update "
                "with severity level: error"
            ),
            promoted_relation=target_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    try:
        statement_recorder.record_many(render_hooks(hooks=entry.post_hook, phase_label="post_hook"))
        with diagnostics_context(sqlbuild_phase="post_hook", sqlbuild_action_name="run"):
            execute_hooks(
                connection=connection,
                adapter=adapter,
                hooks=entry.post_hook,
                phase_label="post_hook",
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
    )


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
    cursor: Any = adapter.execute(connection, discovery_sql)
    row: Any = cursor.fetchone()
    if row is None or row[0] is None or row[1] is None:
        return None
    raw_min: Any = row[0]
    raw_max: Any = row[1]
    min_val: str = raw_min.isoformat() if isinstance(raw_min, datetime) else str(raw_min)
    if isinstance(raw_max, datetime):
        max_val: str = (raw_max + timedelta(seconds=1)).isoformat()
    elif isinstance(raw_max, int):
        max_val = str(raw_max + 1)
    else:
        max_val = str(raw_max)
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
