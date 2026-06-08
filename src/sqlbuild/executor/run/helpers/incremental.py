"""Incremental model execution lifecycle."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import AuditPlanEntry, CursorBounds, ModelPlanEntry
from sqlbuild.compiler.planner.types import IncrementalStrategy, OnSchemaChange
from sqlbuild.executor.auditing.main.execute import execute_audit
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers.contracts import validate_runtime_contract
from sqlbuild.executor.run.helpers.cursor_bounds import (
    has_model_backed_cursor_inputs,
    resolve_runtime_cursor_bounds,
    substitute_cursor_sentinels,
)
from sqlbuild.executor.run.helpers.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run.helpers.hooks import execute_hooks, render_hooks
from sqlbuild.executor.run.helpers.results import build_failed_result
from sqlbuild.executor.run.helpers.type_enforcement import enforce_types_staged
from sqlbuild.executor.run.models import HookExecutionResult, ModelExecutionResult
from sqlbuild.executor.run.types import HookPhase
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.provider.main.runtime import ProviderContainer
from sqlbuild.shared.helpers.diagnostics_logging import diagnostics_context
from sqlbuild.shared.helpers.naming import (
    resolve_destination_qualified_name,
    resolve_qualified_name_parts,
)
from sqlbuild.spec.models.source import SourceEntry

_DEFAULT_ON_SCHEMA_CHANGE: OnSchemaChange = OnSchemaChange.APPEND_NEW_COLUMNS


def execute_incremental_entry(
    *,
    entry: ModelPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    model_targets: dict[str, CompiledRelationDestination],
    seed_targets: dict[str, CompiledRelationDestination],
    source_map: dict[str, SourceEntry],
    model_audits: tuple[AuditPlanEntry, ...],
    declared_columns: tuple[ColumnInfo, ...],
    run_id: str,
    query_change_tracking: bool,
    hook_functions: tuple[DiscoveredHookFunction, ...] = (),
    effective_target_name: str | None = None,
    effective_vars: Mapping[str, object] | None = None,
    providers: ProviderContainer | None = None,
) -> ModelExecutionResult:
    """Execute one incremental model through its delta/DML lifecycle."""

    target_database: str | None = entry.destination.database
    target_schema: str | None = entry.destination.schema
    target_table: str = entry.destination.name
    target_qualified: str = resolve_destination_qualified_name(
        adapter=adapter, target=entry.destination
    )
    delta_table: str = f"{target_table}__delta"
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
    runtime_owned_cursor_bounds: bool = has_model_backed_cursor_inputs(entry.cursor_input_relations)
    runtime_cursor_bounds: CursorBounds | None = None
    resolved_sql: str = entry.resolved_sql

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
        if runtime_owned_cursor_bounds:
            if entry.cursor_column is None:
                raise ExecutorInputError("runtime-owned cursor resolution requires cursor_column")
            runtime_cursor_bounds = resolve_runtime_cursor_bounds(
                adapter=adapter,
                connection=connection,
                target_relation=target_qualified,
                cursor_column=entry.cursor_column,
                cursor_type=entry.cursor_type,
                cursor_grain=entry.cursor_grain,
                cursor_start=entry.cursor_start,
                cursor_input_relations=entry.cursor_input_relations,
            )
            if runtime_cursor_bounds is None:
                raise ExecutorInputError(
                    f"runtime cursor bounds could not be resolved for '{entry.name}'"
                )
            resolved_sql = substitute_cursor_sentinels(
                sql=entry.resolved_sql, bounds=runtime_cursor_bounds
            )
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
                sql=resolved_sql,
                statement_recorder=statement_recorder,
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
            hook_results=hook_results,
        )

    try:
        with diagnostics_context(sqlbuild_phase="schema_change", sqlbuild_action_name="inspect"):
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
            target_columns = adapter.get_columns(
                connection,
                database=target_database,
                schema=target_schema,
                name=target_table,
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

    if entry.type_enforcement and declared_columns:
        try:
            with diagnostics_context(
                sqlbuild_phase="type_enforcement", sqlbuild_action_name="rebuild_delta"
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
                error=str(exc),
                staging_relation=delta_qualified,
                warnings=warnings,
                audit_results=audit_results,
                statement_recorder=statement_recorder,
            )

    try:
        with diagnostics_context(sqlbuild_phase="contract", sqlbuild_action_name="validate_delta"):
            delta_columns = adapter.get_columns(
                connection,
                database=target_database,
                schema=target_schema,
                name=delta_table,
            )
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
                f"delta audit for '{entry.name}' failed before target update "
                "with severity level: error"
            ),
            staging_relation=delta_qualified,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
        )

    effective_bounds: CursorBounds | None = runtime_cursor_bounds or entry.cursor_bounds
    cursor_start: str | None = effective_bounds.start if effective_bounds else None
    cursor_end: str | None = effective_bounds.end if effective_bounds else None

    try:
        with diagnostics_context(sqlbuild_phase="dml", sqlbuild_action_name="apply"):
            _execute_dml(
                adapter=adapter,
                connection=connection,
                target_qualified=target_qualified,
                delta_qualified=delta_qualified,
                target_columns=target_columns,
                delta_columns=delta_columns,
                entry=entry,
                cursor_start=cursor_start,
                cursor_end=cursor_end,
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
        hook_results=tuple(hook_results),
    )


def _apply_schema_change(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_qualified: str,
    target_columns: tuple[ColumnInfo, ...],
    delta_columns: tuple[ColumnInfo, ...],
    on_schema_change: OnSchemaChange,
    warnings: list[str],
    statement_recorder: StatementRecorder,
) -> None:
    """Inspect runtime schema diff and apply on_schema_change policy."""

    target_map: dict[str, str] = {col.name.lower(): col.type for col in target_columns}
    delta_map: dict[str, str] = {col.name.lower(): col.type for col in delta_columns}

    added: list[ColumnInfo] = []
    removed: list[str] = []
    type_changed: list[ColumnInfo] = []

    col: ColumnInfo
    for col in delta_columns:
        col_lower: str = col.name.lower()
        if col_lower not in target_map:
            added.append(col)
        elif target_map[col_lower].upper() != col.type.upper():
            type_changed.append(col)

    for col in target_columns:
        col_lower = col.name.lower()
        if col_lower not in delta_map:
            removed.append(col.name)

    has_diff: bool = bool(added or removed or type_changed)

    if not has_diff:
        return

    if on_schema_change == OnSchemaChange.FAIL:
        diff_parts: list[str] = []
        if added:
            diff_parts.append(f"added columns: {', '.join(c.name for c in added)}")
        if removed:
            diff_parts.append(f"removed columns: {', '.join(removed)}")
        if type_changed:
            diff_parts.append(f"type changes: {', '.join(c.name for c in type_changed)}")
        raise ExecutorInputError(
            f"schema change detected and on_schema_change is set to fail: {'; '.join(diff_parts)}"
        )

    if on_schema_change == OnSchemaChange.IGNORE:
        if added:
            warnings.append(
                f"schema change ignored: new columns in delta not added to target: "
                f"{', '.join(c.name for c in added)}"
            )
        if removed:
            warnings.append(
                f"schema change ignored: target columns not in delta: {', '.join(removed)}"
            )
        if type_changed:
            warnings.append(
                f"schema change ignored: type changes detected: "
                f"{', '.join(c.name for c in type_changed)}"
            )
        return

    if on_schema_change == OnSchemaChange.APPEND_NEW_COLUMNS:
        if added:
            adapter.add_columns(
                connection,
                target=target_qualified,
                columns=tuple(added),
                statement_recorder=statement_recorder,
            )
        if type_changed:
            raise ExecutorInputError(
                f"append_new_columns does not support type changes: "
                f"{', '.join(c.name for c in type_changed)}"
            )
        return

    if on_schema_change == OnSchemaChange.SYNC_ALL_COLUMNS:
        if added:
            adapter.add_columns(
                connection,
                target=target_qualified,
                columns=tuple(added),
                statement_recorder=statement_recorder,
            )
        if removed:
            adapter.drop_columns(
                connection,
                target=target_qualified,
                column_names=tuple(removed),
                statement_recorder=statement_recorder,
            )
        if type_changed:
            adapter.alter_column_types(
                connection,
                target=target_qualified,
                columns=tuple(type_changed),
                statement_recorder=statement_recorder,
            )
        return

    return


def _execute_dml(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_qualified: str,
    delta_qualified: str,
    target_columns: tuple[ColumnInfo, ...],
    delta_columns: tuple[ColumnInfo, ...],
    entry: ModelPlanEntry,
    cursor_start: str | None = None,
    cursor_end: str | None = None,
    statement_recorder: StatementRecorder,
) -> None:
    """Execute the incremental DML strategy from delta into target."""

    strategy: str | None = entry.incremental_strategy
    unique_key: tuple[str, ...] = entry.unique_key

    target_col_set: frozenset[str] = frozenset(col.name.lower() for col in target_columns)
    delta_col_set: frozenset[str] = frozenset(col.name.lower() for col in delta_columns)
    intersection_names: tuple[str, ...] = tuple(
        col.name for col in delta_columns if col.name.lower() in target_col_set
    )
    columns_match: bool = target_col_set == delta_col_set
    dml_columns: tuple[str, ...] | None = None if columns_match else intersection_names
    projection: str = ", ".join(intersection_names) if not columns_match else "*"
    dml_sql: str = f"SELECT {projection} FROM {delta_qualified}"

    if strategy == IncrementalStrategy.APPEND:
        adapter.append(
            connection,
            target=target_qualified,
            sql=dml_sql,
            columns=dml_columns,
            statement_recorder=statement_recorder,
        )
        return

    if strategy == IncrementalStrategy.DELETE_INSERT:
        cursor_column: str | None = entry.cursor_column
        if cursor_column is not None:
            if cursor_start is None or cursor_end is None:
                raise ExecutorInputError(
                    f"cursor-based delete_insert for '{entry.name}' requires both "
                    f"cursor_start and cursor_end but got "
                    f"cursor_start={cursor_start}, cursor_end={cursor_end}"
                )
            adapter.delete_insert_cursor(
                connection,
                target=target_qualified,
                sql=dml_sql,
                cursor_column=cursor_column,
                cursor_start=cursor_start,
                cursor_end=cursor_end,
                columns=dml_columns,
                statement_recorder=statement_recorder,
            )
        else:
            adapter.delete_insert(
                connection,
                target=target_qualified,
                sql=dml_sql,
                unique_key=unique_key,
                columns=dml_columns,
                statement_recorder=statement_recorder,
            )
        return

    if strategy == IncrementalStrategy.MERGE:
        merge_projection: str = ", ".join(intersection_names)
        merge_sql: str = f"SELECT {merge_projection} FROM {delta_qualified}"
        adapter.merge(
            connection,
            target=target_qualified,
            sql=merge_sql,
            unique_key=unique_key,
            statement_recorder=statement_recorder,
        )
        return

    raise ExecutorInputError(f"unsupported incremental strategy: {strategy}")
