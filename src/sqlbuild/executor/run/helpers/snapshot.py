"""Snapshot model execution lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, NormalizedType, StatementRecorder
from sqlbuild.adapter.shared.type_normalization import normalize_type, types_equal
from sqlbuild.adapter.shared.types import TypeFamily
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.compiler.planner.types import (
    HistoricalInput,
    PlanReason,
    SnapshotSchemaChangePolicy,
    SnapshotStrategy,
)
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.contracts import validate_runtime_contract
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks, render_hooks
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.models import HookExecutionResult, ModelExecutionResult
from sqlbuild.executor.run.types import HookPhase
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.helpers.diagnostics_logging import diagnostics_context
from sqlbuild.shared.helpers.naming import (
    resolve_qualified_name_parts,
    resolve_relation_location_qualified_name,
)
from sqlbuild.spec.models.project import SnapshotsConfig
from sqlbuild.spec.models.source import SourceEntry

_DEFAULT_VALID_FROM_COLUMN: str = "valid_from"
_DEFAULT_VALID_TO_COLUMN: str = "valid_to"
_SCHEMA_CHANGE_STRICTNESS: dict[SnapshotSchemaChangePolicy, int] = {
    SnapshotSchemaChangePolicy.APPEND_NEW_COLUMNS: 0,
    SnapshotSchemaChangePolicy.REQUIRE_CONFIRMATION: 1,
    SnapshotSchemaChangePolicy.DENY: 2,
}


def execute_snapshot_entry(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    run_id: str,
    query_change_tracking: bool,
    snapshots: SnapshotsConfig | None = None,
    allow_snapshot_schema_change: bool = False,
    hook_functions: tuple[DiscoveredHookFunction, ...] = (),
    effective_target_name: str | None = None,
    effective_vars: Mapping[str, object] | None = None,
    providers: ProviderContainer | None = None,
) -> ModelExecutionResult:
    """Execute one current-state snapshot model."""

    target_database: str | None = entry.destination.database
    target_schema: str | None = entry.destination.schema
    target_table: str = entry.destination.name
    target_qualified: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=entry.destination
    )
    delta_table: str = f"{target_table}__snapshot_delta"
    delta_qualified: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=target_database,
        schema=target_schema,
        name=delta_table,
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []
    hook_results: list[HookExecutionResult] = []
    statement_recorder: StatementRecorder = StatementRecorder()

    try:
        _validate_supported_snapshot(entry)
        adapter.ensure_schema(
            connection,
            database=target_database,
            schema=target_schema,
            statement_recorder=statement_recorder,
        )
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
        with diagnostics_context(sqlbuild_phase="materialize", sqlbuild_action_name="create_delta"):
            adapter.drop(
                connection,
                destination=delta_qualified,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
            adapter.create_table_as(
                connection,
                destination=delta_qualified,
                sql=entry.resolved_sql,
                statement_recorder=statement_recorder,
            )
            delta_columns: tuple[ColumnInfo, ...] = adapter.get_columns(
                connection,
                database=target_database,
                schema=target_schema,
                name=delta_table,
            )
            check_columns: tuple[str, ...] = _expanded_check_columns(
                entry=entry, delta_columns=delta_columns
            )
            _validate_delta_columns(
                entry=entry, delta_columns=delta_columns, check_columns=check_columns
            )
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
        with diagnostics_context(sqlbuild_phase="contract", sqlbuild_action_name="validate_delta"):
            validate_runtime_contract(
                entry=entry,
                actual_columns=delta_columns,
                dialect=adapter.sql_analysis_dialect_name,
            )
    except Exception as exc:
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.CONTRACT,
            error=exc,
            staging_relation=delta_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    delta_audit_results: tuple[AuditExecutionResult, ...] = _execute_snapshot_delta_audits(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_locations=model_locations,
        seed_locations=seed_locations,
        source_map=source_map,
        model_audits=model_audits,
        delta_qualified=delta_qualified,
    )
    audit_results.extend(delta_audit_results)

    if any(result.outcome == AuditOutcome.ERROR for result in delta_audit_results):
        return build_failed_result(
            entry=entry,
            phase=ExecutionPhase.AUDIT,
            error=(
                f"delta audit for '{entry.name}' failed before target update "
                "with severity level: error"
            ),
            staging_relation=delta_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    try:
        with diagnostics_context(sqlbuild_phase="dml", sqlbuild_action_name="apply_snapshot"):
            if entry.reason == PlanReason.FULL_REFRESH:
                adapter.drop(
                    connection,
                    destination=target_qualified,
                    if_exists=True,
                    statement_recorder=statement_recorder,
                )
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
                    delta_columns=delta_columns,
                    check_columns=check_columns,
                    statement_recorder=statement_recorder,
                )
            else:
                target_columns: tuple[ColumnInfo, ...] = adapter.get_columns(
                    connection,
                    database=target_database,
                    schema=target_schema,
                    name=target_table,
                )
                _apply_snapshot_schema_change(
                    adapter=adapter,
                    connection=connection,
                    entry=entry,
                    snapshots=snapshots or SnapshotsConfig(),
                    target_qualified=target_qualified,
                    target_columns=target_columns,
                    delta_columns=delta_columns,
                    allow_snapshot_schema_change=allow_snapshot_schema_change,
                    statement_recorder=statement_recorder,
                )
                _apply_snapshot_changes(
                    adapter=adapter,
                    connection=connection,
                    entry=entry,
                    target_qualified=target_qualified,
                    delta_qualified=delta_qualified,
                    delta_columns=delta_columns,
                    check_columns=check_columns,
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
            model_locations=model_locations,
            seed_locations=seed_locations,
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
            staging_relation=delta_qualified,
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

    with diagnostics_context(sqlbuild_phase="cleanup", sqlbuild_action_name="drop_delta"):
        adapter.drop(
            connection,
            destination=delta_qualified,
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
        hook_results=tuple(hook_results),
    )


def _execute_snapshot_delta_audits(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_locations: dict[str, CompiledRelationLocation],
    seed_locations: dict[str, CompiledRelationLocation],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    delta_qualified: str,
) -> tuple[AuditExecutionResult, ...]:
    """Run snapshot delta-and-final audits against the pre-DML delta relation."""

    delta_overrides: dict[str, str] = {entry.name: delta_qualified}
    audit_results: list[AuditExecutionResult] = []
    audit: AuditPlanEntry
    for audit in model_audits:
        if audit.effective_run_scope != AuditRunScope.DELTA_AND_FINAL:
            continue
        result: AuditExecutionResult = execute_audit(
            audit=audit,
            adapter=adapter,
            connection=connection,
            model_locations=model_locations,
            seed_locations=seed_locations,
            source_map=source_map,
            relation_overrides=delta_overrides,
            run_scope_phase=AuditRunScope.DELTA_AND_FINAL,
        )
        audit_results.append(result)
    return tuple(audit_results)


def _validate_supported_snapshot(entry: ModelPlanEntry) -> None:
    if entry.snapshot_strategy not in (SnapshotStrategy.TIMESTAMP, SnapshotStrategy.CHECK):
        raise ExecutorInputError(
            "snapshot execution currently supports snapshot_strategy=timestamp or check"
        )
    if (
        entry.observed_at_column is not None
        and entry.invalidate_hard_deletes
        and entry.historical_input == HistoricalInput.CHANGES
    ):
        raise ExecutorInputError("snapshot execution does not support historical hard deletes yet")
    if entry.snapshot_strategy == SnapshotStrategy.TIMESTAMP and entry.updated_at_column is None:
        raise ExecutorInputError("timestamp snapshot execution requires updated_at")
    if entry.snapshot_strategy == SnapshotStrategy.CHECK and not entry.check_columns:
        raise ExecutorInputError("check snapshot execution requires check_columns")
    if not entry.unique_key:
        raise ExecutorInputError("snapshot execution requires unique_key")


def _validate_delta_columns(
    *,
    entry: ModelPlanEntry,
    delta_columns: tuple[ColumnInfo, ...],
    check_columns: tuple[str, ...],
) -> None:
    column_names: frozenset[str] = frozenset(column.name.lower() for column in delta_columns)
    required_columns: tuple[str, ...]
    if entry.snapshot_strategy == SnapshotStrategy.TIMESTAMP:
        required_columns = (*entry.unique_key, _require_updated_at(entry))
        if entry.observed_at_column is not None:
            required_columns = (*required_columns, entry.observed_at_column)
    elif entry.snapshot_strategy == SnapshotStrategy.CHECK:
        required_columns = (*entry.unique_key, *check_columns)
        if entry.observed_at_column is not None:
            required_columns = (*required_columns, entry.observed_at_column)
    else:
        required_columns = entry.unique_key
    if entry.initial_valid_from == "updated_at":
        required_columns = (*required_columns, _require_updated_at(entry))
    if entry.initial_valid_from == "observed_at" and entry.observed_at_column is not None:
        required_columns = (*required_columns, entry.observed_at_column)
    missing_columns: list[str] = [
        column for column in required_columns if column.lower() not in column_names
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
    identity_columns: tuple[str, ...] = entry.unique_key
    if (
        entry.snapshot_strategy == SnapshotStrategy.TIMESTAMP
        and entry.observed_at_column is not None
        and entry.historical_input == HistoricalInput.CHANGES
    ):
        identity_columns = (*identity_columns, _require_updated_at(entry))
    elif entry.observed_at_column is not None:
        identity_columns = (*identity_columns, entry.observed_at_column)
    key_list: str = ", ".join(identity_columns)
    duplicate_sql: str = (
        f"SELECT COUNT(*) FROM (SELECT {key_list} FROM {delta_qualified} "
        f"GROUP BY {key_list} HAVING COUNT(*) > 1) AS __snapshot_duplicate_keys"
    )
    cursor: Any = adapter.execute(connection, duplicate_sql)
    row: tuple[Any, ...] | None = cursor.fetchone()
    if row is not None and int(row[0]) > 0:
        identity_label: str = (
            "snapshot identity" if entry.observed_at_column is not None else "unique_key"
        )
        raise ExecutorInputError(
            f"snapshot model '{entry.name}' source query returned multiple rows for the same "
            f"{identity_label} ({key_list})"
        )


def _create_initial_snapshot_target(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelPlanEntry,
    target_qualified: str,
    delta_qualified: str,
    delta_columns: tuple[ColumnInfo, ...],
    check_columns: tuple[str, ...],
    statement_recorder: StatementRecorder,
) -> None:
    valid_from_column: str = _valid_from_column(entry)
    valid_to_column: str = _valid_to_column(entry)
    if (
        entry.snapshot_strategy == SnapshotStrategy.TIMESTAMP
        and entry.observed_at_column is not None
    ):
        updated_at_column: str = _require_updated_at(entry)
        output_columns: tuple[str, ...] = tuple(column.name for column in delta_columns)
        if entry.historical_input == HistoricalInput.CHANGES:
            statements: tuple[str, ...] = (
                adapter.render_create_initial_historical_timestamp_changes_target(
                    target=target_qualified,
                    source=delta_qualified,
                    unique_key=entry.unique_key,
                    updated_at_column=updated_at_column,
                    valid_from_column=valid_from_column,
                    valid_to_column=valid_to_column,
                    output_columns=output_columns,
                )
            )
        else:
            statements = adapter.render_create_initial_historical_timestamp_snapshot_target(
                target=target_qualified,
                source=delta_qualified,
                unique_key=entry.unique_key,
                updated_at_column=updated_at_column,
                observed_at_column=entry.observed_at_column,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                output_columns=output_columns,
                invalidate_hard_deletes=entry.invalidate_hard_deletes,
            )
    elif entry.snapshot_strategy == SnapshotStrategy.CHECK and entry.observed_at_column is not None:
        output_columns: tuple[str, ...] = tuple(column.name for column in delta_columns)
        statements = adapter.render_create_initial_historical_check_snapshot_target(
            target=target_qualified,
            source=delta_qualified,
            unique_key=entry.unique_key,
            check_columns=check_columns,
            observed_at_column=entry.observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
            invalidate_hard_deletes=entry.invalidate_hard_deletes,
        )
    else:
        statements = adapter.render_create_initial_snapshot_target(
            target=target_qualified,
            source=delta_qualified,
            snapshot_strategy=entry.snapshot_strategy,
            updated_at_column=entry.updated_at_column,
            observed_at_column=entry.observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            initial_valid_from=entry.initial_valid_from,
        )
    statement_recorder.record_many(statements)
    statement: str
    for statement in statements:
        adapter.execute(connection, statement)


def _apply_snapshot_changes(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelPlanEntry,
    target_qualified: str,
    delta_qualified: str,
    delta_columns: tuple[ColumnInfo, ...],
    check_columns: tuple[str, ...],
    statement_recorder: StatementRecorder,
) -> None:
    if entry.snapshot_strategy == SnapshotStrategy.TIMESTAMP:
        _apply_timestamp_snapshot_changes(
            adapter=adapter,
            connection=connection,
            entry=entry,
            target_qualified=target_qualified,
            delta_qualified=delta_qualified,
            delta_columns=delta_columns,
            statement_recorder=statement_recorder,
        )
        return
    if entry.snapshot_strategy == SnapshotStrategy.CHECK:
        _apply_check_snapshot_changes(
            adapter=adapter,
            connection=connection,
            entry=entry,
            target_qualified=target_qualified,
            delta_qualified=delta_qualified,
            delta_columns=delta_columns,
            check_columns=check_columns,
            statement_recorder=statement_recorder,
        )
        return
    raise ExecutorInputError(f"unsupported snapshot strategy: {entry.snapshot_strategy}")


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
    output_columns: tuple[str, ...] = tuple(column.name for column in delta_columns)
    if entry.observed_at_column is not None:
        statements: tuple[str, ...]
        if entry.historical_input == HistoricalInput.CHANGES:
            statements = adapter.render_apply_historical_timestamp_changes(
                target=target_qualified,
                source=delta_qualified,
                unique_key=entry.unique_key,
                updated_at_column=updated_at_column,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                output_columns=output_columns,
            )
        else:
            statements = adapter.render_apply_historical_timestamp_snapshot_changes(
                target=target_qualified,
                source=delta_qualified,
                unique_key=entry.unique_key,
                updated_at_column=updated_at_column,
                observed_at_column=entry.observed_at_column,
                valid_from_column=valid_from_column,
                valid_to_column=valid_to_column,
                output_columns=output_columns,
                invalidate_hard_deletes=entry.invalidate_hard_deletes,
            )
        statement_recorder.record_many(statements)
        with adapter.transaction(connection):
            statement: str
            for statement in statements:
                adapter.execute(connection, statement)
        return
    statements: tuple[str, ...] = adapter.render_apply_timestamp_snapshot_changes(
        target=target_qualified,
        source=delta_qualified,
        unique_key=entry.unique_key,
        updated_at_column=updated_at_column,
        observed_at_column=entry.observed_at_column,
        valid_from_column=valid_from_column,
        valid_to_column=valid_to_column,
        initial_valid_from=entry.initial_valid_from,
        output_columns=output_columns,
        invalidate_hard_deletes=entry.invalidate_hard_deletes,
    )
    statement_recorder.record_many(statements)
    with adapter.transaction(connection):
        statement: str
        for statement in statements:
            adapter.execute(connection, statement)


def _apply_check_snapshot_changes(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelPlanEntry,
    target_qualified: str,
    delta_qualified: str,
    delta_columns: tuple[ColumnInfo, ...],
    check_columns: tuple[str, ...],
    statement_recorder: StatementRecorder,
) -> None:
    valid_from_column: str = _valid_from_column(entry)
    valid_to_column: str = _valid_to_column(entry)
    output_columns: tuple[str, ...] = tuple(column.name for column in delta_columns)
    if entry.observed_at_column is not None:
        statements: tuple[str, ...] = adapter.render_apply_historical_check_snapshot_changes(
            target=target_qualified,
            source=delta_qualified,
            unique_key=entry.unique_key,
            check_columns=check_columns,
            observed_at_column=entry.observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            output_columns=output_columns,
            invalidate_hard_deletes=entry.invalidate_hard_deletes,
        )
    else:
        statements = adapter.render_apply_check_snapshot_changes(
            target=target_qualified,
            source=delta_qualified,
            unique_key=entry.unique_key,
            check_columns=check_columns,
            updated_at_column=entry.updated_at_column,
            observed_at_column=entry.observed_at_column,
            valid_from_column=valid_from_column,
            valid_to_column=valid_to_column,
            initial_valid_from=entry.initial_valid_from,
            output_columns=output_columns,
            invalidate_hard_deletes=entry.invalidate_hard_deletes,
        )
    statement_recorder.record_many(statements)
    with adapter.transaction(connection):
        statement: str
        for statement in statements:
            adapter.execute(connection, statement)


def _expanded_check_columns(
    *, entry: ModelPlanEntry, delta_columns: tuple[ColumnInfo, ...]
) -> tuple[str, ...]:
    if entry.snapshot_strategy != SnapshotStrategy.CHECK or entry.check_columns != ("*",):
        return entry.check_columns

    excluded_names: set[str] = {column.lower() for column in entry.unique_key}
    excluded_names.add(_valid_from_column(entry).lower())
    excluded_names.add(_valid_to_column(entry).lower())
    if entry.observed_at_column is not None:
        excluded_names.add(entry.observed_at_column.lower())
    if entry.updated_at_column is not None:
        excluded_names.add(entry.updated_at_column.lower())

    expanded_columns: tuple[str, ...] = tuple(
        column.name for column in delta_columns if column.name.lower() not in excluded_names
    )
    if not expanded_columns:
        raise ExecutorInputError(
            f"snapshot model '{entry.name}' check_columns [*] did not match any data columns"
        )
    return expanded_columns


def _apply_snapshot_schema_change(
    *,
    adapter: BaseAdapter,
    connection: Any,
    entry: ModelPlanEntry,
    snapshots: SnapshotsConfig,
    target_qualified: str,
    target_columns: tuple[ColumnInfo, ...],
    delta_columns: tuple[ColumnInfo, ...],
    allow_snapshot_schema_change: bool,
    statement_recorder: StatementRecorder,
) -> None:
    target_map: dict[str, ColumnInfo] = {column.name.lower(): column for column in target_columns}

    added: tuple[ColumnInfo, ...] = tuple(
        column for column in delta_columns if column.name.lower() not in target_map
    )
    type_changed: tuple[str, ...] = tuple(
        column.name
        for column in delta_columns
        if column.name.lower() in target_map
        and not _snapshot_types_compatible(
            target_type=target_map[column.name.lower()].type,
            delta_type=column.type,
            dialect=adapter.sql_analysis_dialect(),
        )
    )

    if type_changed:
        raise ExecutorInputError(
            f"snapshot schema change does not support type changes: {', '.join(type_changed)}"
        )
    if not added:
        return

    policy: SnapshotSchemaChangePolicy = _effective_snapshot_schema_change_policy(
        entry=entry, snapshots=snapshots
    )
    added_names: str = ", ".join(column.name for column in added)
    if policy == SnapshotSchemaChangePolicy.DENY:
        raise ExecutorInputError(
            f"snapshot model '{entry.name}' detected new output columns: {added_names}; "
            "snapshot_schema_change is set to deny"
        )
    if (
        policy == SnapshotSchemaChangePolicy.REQUIRE_CONFIRMATION
        and not allow_snapshot_schema_change
    ):
        if entry.snapshot_strategy == SnapshotStrategy.CHECK and entry.check_columns == ("*",):
            raise ExecutorInputError(
                f"snapshot model '{entry.name}' check_columns [*] detected new data columns "
                f"on existing target: {added_names}. These columns would become part of "
                "change detection. Re-run with --allow-snapshot-schema-change to accept, "
                "or use explicit check_columns."
            )
        raise ExecutorInputError(
            f"snapshot model '{entry.name}' detected new output columns: {added_names}; "
            "re-run with --allow-snapshot-schema-change to accept"
        )

    adapter.add_columns(
        connection,
        destination=target_qualified,
        columns=added,
        statement_recorder=statement_recorder,
    )


def _snapshot_types_compatible(*, target_type: str, delta_type: str, dialect: str | None) -> bool:
    if types_equal(left=target_type, right=delta_type, dialect=dialect):
        return True
    target: NormalizedType = normalize_type(type_sql=target_type, dialect=dialect)
    delta: NormalizedType = normalize_type(type_sql=delta_type, dialect=dialect)
    if target.family != TypeFamily.STRING or delta.family != TypeFamily.STRING:
        return False
    if target.length is None:
        return True
    if delta.length is None:
        return False
    return delta.length <= target.length


def _effective_snapshot_schema_change_policy(
    *, entry: ModelPlanEntry, snapshots: SnapshotsConfig
) -> SnapshotSchemaChangePolicy:
    project_policy: SnapshotSchemaChangePolicy = SnapshotSchemaChangePolicy(
        snapshots.wildcard_check_schema_change
        if entry.snapshot_strategy == SnapshotStrategy.CHECK and entry.check_columns == ("*",)
        else snapshots.schema_change
    )
    if entry.snapshot_schema_change is None:
        return project_policy
    model_policy: SnapshotSchemaChangePolicy = SnapshotSchemaChangePolicy(
        entry.snapshot_schema_change
    )
    return max((project_policy, model_policy), key=lambda policy: _SCHEMA_CHANGE_STRICTNESS[policy])


def _require_updated_at(entry: ModelPlanEntry) -> str:
    if entry.updated_at_column is None:
        raise ExecutorInputError("timestamp snapshot execution requires updated_at")
    return entry.updated_at_column


def _valid_from_column(entry: ModelPlanEntry) -> str:
    return entry.valid_from_column or _DEFAULT_VALID_FROM_COLUMN


def _valid_to_column(entry: ModelPlanEntry) -> str:
    return entry.valid_to_column or _DEFAULT_VALID_TO_COLUMN
