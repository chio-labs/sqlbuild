"""Incremental model execution lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
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
from sqlbuild.compiler.planner.models import CursorBounds, ModelPlanEntry
from sqlbuild.compiler.planner.types import IncrementalStrategy, OnSchemaChange, RelationReuseKind
from sqlbuild.diagnostics.main.diagnostics_context import diagnostics_context
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
from sqlbuild.executor.run._helpers.execution.promotion import promote_relation_to_destination
from sqlbuild.executor.run._helpers.execution.results import (
    build_failed_result,
    build_skipped_result,
)
from sqlbuild.executor.run._helpers.reuse.core import (
    create_relation_from_reuse_plan,
)
from sqlbuild.executor.run._helpers.reuse.fingerprinting import try_write_fingerprint
from sqlbuild.executor.run._helpers.validation.contracts import validate_runtime_contract
from sqlbuild.executor.run._helpers.validation.cursor_bounds import (
    has_model_backed_cursor_inputs,
    resolve_runtime_cursor_bounds,
    substitute_cursor_sentinels,
)
from sqlbuild.executor.run._helpers.validation.type_enforcement import enforce_types_staged
from sqlbuild.executor.run.models import (
    FinalAuditRun,
    HookExecutionResult,
    ModelExecutionResult,
    ModelMaterializationContext,
    PostHookPhaseOutcome,
    RuntimeCursorSpec,
)
from sqlbuild.executor.run.types import ExecutionPhase
from sqlbuild.executor.scheduling.types import ExecutionStatus

_DEFAULT_ON_SCHEMA_CHANGE: OnSchemaChange = OnSchemaChange.APPEND_NEW_COLUMNS


@dataclass(frozen=True)
class _DeltaPreparation:
    """Resolved SQL and runtime cursor bounds after delta relation staging."""

    resolved_sql: str
    runtime_cursor_bounds: CursorBounds | None


def execute_incremental_entry(
    *,
    context: ModelMaterializationContext,
    declared_columns: tuple[ColumnInfo, ...],
) -> ModelExecutionResult:
    """Execute one incremental model through its delta/DML lifecycle."""

    entry: ModelPlanEntry = context.entry
    adapter: BaseAdapter = context.adapter
    connection: Any = context.connection
    target_database: str | None = entry.destination.database
    target_schema: str | None = entry.destination.schema
    target_table: str = entry.destination.name
    target_qualified: str = resolve_relation_location_qualified_name(
        adapter=adapter, location=entry.destination
    )
    delta_table: str = f"{target_table}__delta"
    delta_qualified: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=target_database,
        schema=target_schema,
        name=delta_table,
    )
    seed_table: str = f"{target_table}__reuse_seed"
    seed_qualified: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=target_database,
        schema=target_schema,
        name=seed_table,
    )
    warnings: list[str] = []
    audit_results: list[AuditExecutionResult] = []
    hook_results: list[HookExecutionResult] = []
    statement_recorder: StatementRecorder = StatementRecorder()

    pre_hook_exit: ModelExecutionResult | None = run_pre_hook_phase(
        context=context,
        warnings=warnings,
        audit_results=audit_results,
        hook_results=hook_results,
        statement_recorder=statement_recorder,
    )
    if pre_hook_exit is not None:
        return pre_hook_exit

    try:
        preparation: _DeltaPreparation = _prepare_delta_relation(
            context=context,
            target_database=target_database,
            target_schema=target_schema,
            target_table=target_table,
            target_qualified=target_qualified,
            seed_qualified=seed_qualified,
            delta_qualified=delta_qualified,
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
                connection=connection,
                database=target_database,
                schema=target_schema,
                name=delta_table,
            )
            target_columns: tuple[ColumnInfo, ...] = adapter.get_columns(
                connection=connection,
                database=target_database,
                schema=target_schema,
                name=target_table,
            )
            warnings.extend(
                _apply_schema_change(
                    adapter=adapter,
                    connection=connection,
                    target_qualified=target_qualified,
                    target_columns=target_columns,
                    delta_columns=delta_columns,
                    on_schema_change=entry.on_schema_change or _DEFAULT_ON_SCHEMA_CHANGE,
                    statement_recorder=statement_recorder,
                )
            )
            target_columns = adapter.get_columns(
                connection=connection,
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
                connection=connection,
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

    delta_audit_run: FinalAuditRun = run_delta_scope_audits(
        context=context, delta_qualified=delta_qualified
    )
    audit_results.extend(delta_audit_run.results)

    if delta_audit_run.has_error:
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

    effective_bounds: CursorBounds | None = preparation.runtime_cursor_bounds or entry.cursor_bounds
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

    final_audit_run: FinalAuditRun = run_final_scope_audits(context=context)
    audit_results.extend(final_audit_run.results)

    if final_audit_run.has_error:
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

    post_hook_outcome: PostHookPhaseOutcome = run_post_hook_phase(
        context=context,
        warnings=warnings,
        audit_results=audit_results,
        hook_results=hook_results,
        statement_recorder=statement_recorder,
        staging_relation=delta_qualified,
        promoted_relation=target_qualified,
    )
    if post_hook_outcome.failure is not None:
        return post_hook_outcome.failure
    if post_hook_outcome.skipped:
        with diagnostics_context(sqlbuild_phase="cleanup", sqlbuild_action_name="drop_delta"):
            adapter.drop(
                connection=connection,
                destination=delta_qualified,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        return build_skipped_result(
            entry=entry,
            warnings=warnings,
            audit_results=audit_results,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
            promoted_relation=target_qualified,
        )

    warnings.extend(
        try_write_fingerprint(
            entry=entry,
            adapter=adapter,
            connection=connection,
            run_id=context.run_id,
            query_change_tracking=context.query_change_tracking,
            model_audits=context.model_audits,
            audit_results=tuple(audit_results),
        )
    )

    with diagnostics_context(sqlbuild_phase="cleanup", sqlbuild_action_name="drop_delta"):
        adapter.drop(
            connection=connection,
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


def _prepare_delta_relation(
    *,
    context: ModelMaterializationContext,
    target_database: str | None,
    target_schema: str | None,
    target_table: str,
    target_qualified: str,
    seed_qualified: str,
    delta_qualified: str,
    statement_recorder: StatementRecorder,
) -> _DeltaPreparation:
    """Seed reuse, resolve runtime cursors, and create the delta relation."""

    entry: ModelPlanEntry = context.entry
    adapter: BaseAdapter = context.adapter
    connection: Any = context.connection
    runtime_cursor_bounds: CursorBounds | None = None
    resolved_sql: str = entry.resolved_sql
    adapter.ensure_schema(
        connection=connection,
        database=target_database,
        schema=target_schema,
        statement_recorder=statement_recorder,
    )
    if (
        entry.relation_reuse is not None
        and entry.relation_reuse.kind == RelationReuseKind.SEEDED_RELATION_REUSE
    ):
        adapter.drop(
            connection=connection,
            destination=seed_qualified,
            if_exists=True,
            statement_recorder=statement_recorder,
        )
        create_relation_from_reuse_plan(
            adapter=adapter,
            connection=connection,
            model_name=entry.name,
            expected_version_hash=entry.fingerprint_version_hash,
            relation_reuse=entry.relation_reuse,
            destination_relation=seed_qualified,
            statement_recorder=statement_recorder,
        )
        promote_relation_to_destination(
            adapter=adapter,
            connection=connection,
            origin_relation=seed_qualified,
            destination_relation=target_qualified,
            destination_database=target_database,
            destination_schema=target_schema,
            destination_name=target_table,
            statement_recorder=statement_recorder,
        )
    if has_model_backed_cursor_inputs(entry.cursor_input_relations):
        if entry.cursor_column is None:
            raise ExecutorInputError("runtime-owned cursor resolution requires cursor_column")
        runtime_cursor_bounds = resolve_runtime_cursor_bounds(
            adapter=adapter,
            connection=connection,
            target_relation=target_qualified,
            target_database=target_database,
            target_schema=target_schema,
            target_name=target_table,
            spec=RuntimeCursorSpec(
                cursor_column=entry.cursor_column,
                cursor_type=entry.cursor_type,
                cursor_grain=entry.cursor_grain,
                cursor_start=entry.cursor_start,
                cursor_input_relations=entry.cursor_input_relations,
            ),
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
            connection=connection,
            destination=delta_qualified,
            if_exists=True,
            statement_recorder=statement_recorder,
        )
        adapter.create_table_as(
            connection=connection,
            destination=delta_qualified,
            sql=resolved_sql,
            statement_recorder=statement_recorder,
        )
    return _DeltaPreparation(
        resolved_sql=resolved_sql,
        runtime_cursor_bounds=runtime_cursor_bounds,
    )


def _apply_schema_change(
    *,
    adapter: BaseAdapter,
    connection: Any,
    target_qualified: str,
    target_columns: tuple[ColumnInfo, ...],
    delta_columns: tuple[ColumnInfo, ...],
    on_schema_change: OnSchemaChange,
    statement_recorder: StatementRecorder,
) -> tuple[str, ...]:
    """Inspect runtime schema diff, apply on_schema_change policy, return new warnings."""

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
        return ()

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
        ignored_warnings: list[str] = []
        if added:
            ignored_warnings.append(
                f"schema change ignored: new columns in delta not added to target: "
                f"{', '.join(c.name for c in added)}"
            )
        if removed:
            ignored_warnings.append(
                f"schema change ignored: target columns not in delta: {', '.join(removed)}"
            )
        if type_changed:
            ignored_warnings.append(
                f"schema change ignored: type changes detected: "
                f"{', '.join(c.name for c in type_changed)}"
            )
        return tuple(ignored_warnings)

    if on_schema_change == OnSchemaChange.APPEND_NEW_COLUMNS:
        if added:
            adapter.add_columns(
                connection=connection,
                destination=target_qualified,
                columns=tuple(added),
                statement_recorder=statement_recorder,
            )
        if type_changed:
            raise ExecutorInputError(
                f"append_new_columns does not support type changes: "
                f"{', '.join(c.name for c in type_changed)}"
            )
        return ()

    if on_schema_change == OnSchemaChange.SYNC_ALL_COLUMNS:
        if added:
            adapter.add_columns(
                connection=connection,
                destination=target_qualified,
                columns=tuple(added),
                statement_recorder=statement_recorder,
            )
        if removed:
            adapter.drop_columns(
                connection=connection,
                destination=target_qualified,
                column_names=tuple(removed),
                statement_recorder=statement_recorder,
            )
        if type_changed:
            adapter.alter_column_types(
                connection=connection,
                destination=target_qualified,
                columns=tuple(type_changed),
                statement_recorder=statement_recorder,
            )
        return ()

    return ()


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
        incremental_adapter: BaseAdapter = adapter
        incremental_adapter.append(
            connection=connection,
            destination=target_qualified,
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
                connection=connection,
                destination=target_qualified,
                sql=dml_sql,
                cursor_column=cursor_column,
                cursor_start=cursor_start,
                cursor_end=cursor_end,
                columns=dml_columns,
                statement_recorder=statement_recorder,
                cursor_type=entry.cursor_type,
            )
        else:
            adapter.delete_insert(
                connection=connection,
                destination=target_qualified,
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
            connection=connection,
            destination=target_qualified,
            sql=merge_sql,
            unique_key=unique_key,
            statement_recorder=statement_recorder,
        )
        return

    raise ExecutorInputError(f"unsupported incremental strategy: {strategy}")
