"""Snapshot model execution lifecycle."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationTarget
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.compiler.planner.types import SnapshotStrategy
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks, render_hooks
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.shared.helpers.diagnostics_logging import diagnostics_context
from sqlbuild.shared.helpers.naming import (
    resolve_qualified_name_parts,
    resolve_target_qualified_name,
)
from sqlbuild.spec.models.source import SourceEntry

_DEFAULT_VALID_FROM_COLUMN: str = "valid_from"
_DEFAULT_VALID_TO_COLUMN: str = "valid_to"


def execute_snapshot_entry(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationTarget],
    seed_targets: dict[str, CompiledRelationTarget],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    run_id: str,
    query_change_tracking: bool,
) -> ModelExecutionResult:
    """Execute one current-state timestamp snapshot model."""

    target_database: str | None = entry.target.database
    target_schema: str | None = entry.target.schema
    target_table: str = entry.target.name
    target_qualified: str = resolve_target_qualified_name(adapter=adapter, target=entry.target)
    delta_table: str = f"{target_table}__snapshot_delta"
    delta_qualified: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=target_database,
        schema=target_schema,
        name=delta_table,
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []
    statement_recorder: StatementRecorder = StatementRecorder()

    try:
        _validate_supported_snapshot(entry)
        adapter.ensure_schema(
            connection,
            database=target_database,
            schema=target_schema,
            statement_recorder=statement_recorder,
        )
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

    try:
        with diagnostics_context(sqlbuild_phase="materialize", sqlbuild_action_name="create_delta"):
            adapter.drop(
                connection,
                target=delta_qualified,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
            adapter.create_table_as(
                connection,
                target=delta_qualified,
                sql=entry.resolved_sql,
                statement_recorder=statement_recorder,
            )
            delta_columns: tuple[ColumnInfo, ...] = adapter.get_columns(
                connection,
                database=target_database,
                schema=target_schema,
                name=delta_table,
            )
            _validate_delta_columns(entry=entry, delta_columns=delta_columns)
            _validate_unique_snapshot_keys(
                adapter=adapter,
                connection=connection,
                entry=entry,
                delta_qualified=delta_qualified,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.STAGING,
            error=str(exc),
            staging_relation=delta_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    try:
        with diagnostics_context(sqlbuild_phase="dml", sqlbuild_action_name="apply_snapshot"):
            target_exists: bool = adapter.relation_exists(
                connection,
                database=target_database,
                schema=target_schema,
                name=target_table,
            )
            if not target_exists:
                _create_initial_snapshot_target(
                    adapter=adapter,
                    connection=connection,
                    entry=entry,
                    target_qualified=target_qualified,
                    delta_qualified=delta_qualified,
                    statement_recorder=statement_recorder,
                )
            else:
                _apply_timestamp_snapshot_changes(
                    adapter=adapter,
                    connection=connection,
                    entry=entry,
                    target_qualified=target_qualified,
                    delta_qualified=delta_qualified,
                    delta_columns=delta_columns,
                    statement_recorder=statement_recorder,
                )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.DML,
            error=str(exc),
            staging_relation=delta_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    final_audit_error: bool = False
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
            final_audit_error = True

    if final_audit_error:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"final audit for '{entry.name}' failed after target update "
                "with severity level: error"
            ),
            staging_relation=delta_qualified,
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
            staging_relation=delta_qualified,
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

    with diagnostics_context(sqlbuild_phase="cleanup", sqlbuild_action_name="drop_delta"):
        adapter.drop(
            connection,
            target=delta_qualified,
            if_exists=True,
            statement_recorder=statement_recorder,
        )

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.SUCCESS,
        promoted_relation=target_qualified,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
    )


def _validate_supported_snapshot(entry: ModelPlanEntry) -> None:
    if entry.snapshot_strategy != SnapshotStrategy.TIMESTAMP:
        raise ExecutorInputError(
            "snapshot execution currently supports snapshot_strategy=timestamp"
        )
    if entry.observed_at_column is not None:
        raise ExecutorInputError("snapshot execution does not support historical observed_at yet")
    if entry.updated_at_column is None:
        raise ExecutorInputError("timestamp snapshot execution requires updated_at")
    if not entry.unique_key:
        raise ExecutorInputError("snapshot execution requires unique_key")


def _validate_delta_columns(
    *, entry: ModelPlanEntry, delta_columns: tuple[ColumnInfo, ...]
) -> None:
    column_names: frozenset[str] = frozenset(column.name.lower() for column in delta_columns)
    updated_at_column: str = _require_updated_at(entry)
    missing_columns: list[str] = [
        column
        for column in (*entry.unique_key, updated_at_column)
        if column.lower() not in column_names
    ]
    if missing_columns:
        raise ExecutorInputError(
            f"snapshot model '{entry.name}' query output is missing required columns: "
            f"{', '.join(missing_columns)}"
        )
    valid_from_column: str = _valid_from_column(entry)
    valid_to_column: str = _valid_to_column(entry)
    generated_collisions: list[str] = [
        column for column in (valid_from_column, valid_to_column) if column.lower() in column_names
    ]
    if generated_collisions:
        raise ExecutorInputError(
            f"snapshot model '{entry.name}' query output includes generated validity columns: "
            f"{', '.join(generated_collisions)}"
        )


def _validate_unique_snapshot_keys(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelPlanEntry,
    delta_qualified: str,
) -> None:
    key_list: str = ", ".join(entry.unique_key)
    duplicate_sql: str = (
        f"SELECT 1 FROM {delta_qualified} GROUP BY {key_list} HAVING COUNT(*) > 1 LIMIT 1"
    )
    cursor: Any = adapter.execute(connection, duplicate_sql)
    if cursor.fetchone() is not None:
        raise ExecutorInputError(
            f"snapshot model '{entry.name}' source query returned multiple rows for the same "
            f"unique_key ({key_list})"
        )


def _create_initial_snapshot_target(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelPlanEntry,
    target_qualified: str,
    delta_qualified: str,
    statement_recorder: StatementRecorder,
) -> None:
    updated_at_column: str = _require_updated_at(entry)
    valid_from_column: str = _valid_from_column(entry)
    valid_to_column: str = _valid_to_column(entry)
    sql: str = (
        f"SELECT *, {updated_at_column} AS {valid_from_column}, "
        f"CAST(NULL AS TIMESTAMP) AS {valid_to_column} FROM {delta_qualified}"
    )
    adapter.create_table_as(
        connection,
        target=target_qualified,
        sql=sql,
        statement_recorder=statement_recorder,
    )


def _apply_timestamp_snapshot_changes(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelPlanEntry,
    target_qualified: str,
    delta_qualified: str,
    delta_columns: tuple[ColumnInfo, ...],
    statement_recorder: StatementRecorder,
) -> None:
    updated_at_column: str = _require_updated_at(entry)
    valid_from_column: str = _valid_from_column(entry)
    valid_to_column: str = _valid_to_column(entry)
    key_condition: str = " AND ".join(
        f"__target.{column} = __source.{column}" for column in entry.unique_key
    )
    close_sql: str = (
        f"UPDATE {target_qualified} AS __target "
        f"SET {valid_to_column} = __source.{updated_at_column} "
        f"FROM {delta_qualified} AS __source "
        f"WHERE {key_condition} "
        f"AND __target.{valid_to_column} IS NULL "
        f"AND __source.{updated_at_column} > __target.{updated_at_column}"
    )
    output_columns: tuple[str, ...] = tuple(column.name for column in delta_columns)
    insert_columns: tuple[str, ...] = (*output_columns, valid_from_column, valid_to_column)
    insert_column_sql: str = ", ".join(insert_columns)
    output_select_sql: str = ", ".join(f"__source.{column}" for column in output_columns)
    active_join_condition: str = " AND ".join(
        f"__active.{column} = __source.{column}" for column in entry.unique_key
    )
    first_key: str = entry.unique_key[0]
    insert_sql: str = (
        f"INSERT INTO {target_qualified} ({insert_column_sql}) "
        f"SELECT {output_select_sql}, __source.{updated_at_column}, CAST(NULL AS TIMESTAMP) "
        f"FROM {delta_qualified} AS __source "
        f"LEFT JOIN {target_qualified} AS __active "
        f"ON {active_join_condition} AND __active.{valid_to_column} IS NULL "
        f"WHERE __active.{first_key} IS NULL "
        f"OR __source.{updated_at_column} > __active.{updated_at_column}"
    )
    statements: tuple[str, ...] = (close_sql, insert_sql)
    statement_recorder.record_many(statements)
    with adapter.transaction(connection):
        statement: str
        for statement in statements:
            adapter.execute(connection, statement)


def _require_updated_at(entry: ModelPlanEntry) -> str:
    if entry.updated_at_column is None:
        raise ExecutorInputError("timestamp snapshot execution requires updated_at")
    return entry.updated_at_column


def _valid_from_column(entry: ModelPlanEntry) -> str:
    return entry.valid_from_column or _DEFAULT_VALID_FROM_COLUMN


def _valid_to_column(entry: ModelPlanEntry) -> str:
    return entry.valid_to_column or _DEFAULT_VALID_TO_COLUMN
