"""Microbatch incremental execution lifecycle."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.models import AuditPlanEntry, CursorBounds, ModelPlanEntry
from sqlbuild.compiler.planner.types import CursorType, OnSchemaChange
from sqlbuild.executor.auditing.main import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks
from sqlbuild.executor.run.helpers.incremental import (
    _apply_schema_change,
    _execute_dml,
)
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.helpers.type_enforcement import enforce_types_staged
from sqlbuild.executor.run.models import BatchWindow, ModelExecutionResult
from sqlbuild.executor.shared.helpers.naming import build_qualified_name
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.spec.models.source import SourceEntry

_DEFAULT_ON_SCHEMA_CHANGE: OnSchemaChange = OnSchemaChange.APPEND_NEW_COLUMNS
_DURATION_PATTERN_STR: str = r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$"


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
    fingerprint_schema: str | None,
    is_full_refresh: bool = False,
) -> ModelExecutionResult:
    """Execute one microbatch incremental model through batched delta/DML."""

    target_database: str | None = entry.target.database
    target_schema: str | None = entry.target.schema
    target_table: str = entry.target.name
    target_qualified: str = build_qualified_name(
        database=target_database, schema=target_schema, name=target_table
    )
    delta_table: str = f"{target_table}__delta"
    delta_qualified: str = build_qualified_name(
        database=target_database, schema=target_schema, name=delta_table
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []

    try:
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
        )

    microbatch_range: CursorBounds | None = entry.microbatch_range
    if is_full_refresh:
        try:
            microbatch_range = _discover_cursor_range(
                adapter=adapter,
                connection=connection,
                resolved_sql=entry.resolved_sql,
                cursor_column=entry.cursor_column,
            )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"failed to discover microbatch cursor range: {exc}",
                warnings=warnings,
                audit_results=audit_results,
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
            )

    if microbatch_range is None:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.STAGING,
            error="microbatch_range is not available and model is not full refresh",
            warnings=warnings,
            audit_results=audit_results,
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
        )

    batches: tuple[BatchWindow, ...] = compute_batch_windows(
        start=microbatch_range.start,
        end=microbatch_range.end,
        batch_size=batch_size,
        cursor_type=cursor_type,
    )

    if not batches:
        return ModelExecutionResult(
            model_name=entry.name,
            status=ExecutionStatus.SUCCESS,
            promoted_relation=target_qualified,
            audit_results=tuple(audit_results),
            warning_messages=(*tuple(warnings), "no batches to process"),
        )

    if is_full_refresh:
        try:
            adapter.drop(connection, target=target_qualified, if_exists=True)
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"failed to drop target for full-refresh microbatch: {exc}",
                warnings=warnings,
                audit_results=audit_results,
            )

    schema_checked: bool = False
    completed_batches: int = 0
    batch: BatchWindow
    for batch in batches:
        batch_sql: str = _substitute_sentinels(
            sql=entry.resolved_sql,
            batch_start=batch.start,
            batch_end=batch.end,
        )

        try:
            adapter.drop(connection, target=delta_qualified, if_exists=True)
            adapter.create_table_as(connection, target=delta_qualified, sql=batch_sql)
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.STAGING,
                error=f"batch {batch.index}: {exc}",
                staging_relation=delta_qualified,
                warnings=warnings,
                audit_results=audit_results,
            )

        if not schema_checked and not is_full_refresh:
            try:
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
                )
            except Exception as exc:
                return build_failed_result(
                    entry=entry,
                    phase=ExecutionPhase.SCHEMA_CHANGE,
                    error=str(exc),
                    staging_relation=delta_qualified,
                    warnings=warnings,
                    audit_results=audit_results,
                )
            schema_checked = True

        if entry.type_enforcement and declared_columns:
            try:
                enforce_types_staged(
                    adapter=adapter,
                    connection=connection,
                    staging_qualified=delta_qualified,
                    staging_database=target_database,
                    staging_schema=target_schema,
                    staging_table=delta_table,
                    declared_columns=declared_columns,
                )
            except Exception as exc:
                return build_failed_result(
                    entry=entry,
                    phase=ExecutionPhase.TYPE_ENFORCEMENT,
                    error=f"batch {batch.index}: {exc}",
                    staging_relation=delta_qualified,
                    warnings=warnings,
                    audit_results=audit_results,
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
                error=f"batch {batch.index}: pre-DML delta audit failed with error severity",
                staging_relation=delta_qualified,
                warnings=warnings,
                audit_results=audit_results,
            )

        try:
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
            if is_full_refresh and completed_batches == 0:
                adapter.create_table_as(
                    connection,
                    target=target_qualified,
                    sql=f"SELECT * FROM {delta_qualified}",
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
                )
        except Exception as exc:
            return build_failed_result(
                entry=entry,
                phase=ExecutionPhase.DML,
                error=f"batch {batch.index}: {exc}",
                staging_relation=delta_qualified,
                warnings=warnings,
                audit_results=audit_results,
            )

        adapter.drop(connection, target=delta_qualified, if_exists=True)
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
            error="post-DML final audit failed with error severity; target was already updated",
            promoted_relation=target_qualified,
            warnings=warnings,
            audit_results=audit_results,
        )

    try:
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
        )

    try_write_fingerprint(
        entry=entry,
        adapter=adapter,
        connection=connection,
        run_id=run_id,
        fingerprint_schema=fingerprint_schema,
        warnings=warnings,
    )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=target_qualified,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
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
    resolved_sql: str,
    cursor_column: str | None,
) -> CursorBounds | None:
    """Discover MIN/MAX cursor range from the model SQL for full-refresh microbatch."""

    if cursor_column is None:
        return None
    clean_sql: str = resolved_sql.replace(
        f"'{MICROBATCH_START_SENTINEL}'", "'1970-01-01T00:00:00'"
    ).replace(f"'{MICROBATCH_END_SENTINEL}'", "'2999-12-31T23:59:59'")
    discovery_sql: str = (
        f"SELECT MIN({cursor_column}), MAX({cursor_column}) "
        f"FROM ({clean_sql}) AS __cursor_discovery"
    )
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
    return CursorBounds(start=min_val, end=max_val)


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
    days: int = int(match.group(1) or 0)
    hours: int = int(match.group(2) or 0)
    minutes: int = int(match.group(3) or 0)
    seconds: int = int(match.group(4) or 0)
    delta: timedelta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    if delta.total_seconds() == 0:
        return ()

    try:
        start_dt: datetime = datetime.fromisoformat(start)
        end_dt: datetime = datetime.fromisoformat(end)
    except ValueError, TypeError:
        return ()

    if start_dt >= end_dt:
        return ()

    windows: list[BatchWindow] = []
    index: int = 0
    current: datetime = start_dt
    while current < end_dt:
        batch_end: datetime = min(current + delta, end_dt)
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
    except InvalidOperation, ValueError, OverflowError:
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
