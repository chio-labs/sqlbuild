"""Test helpers for incremental executor integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationDestination,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    AuditPlanEntry,
    CursorBounds,
    CursorInputRelation,
    ModelPlanEntry,
)
from sqlbuild.compiler.planner.types import (
    IncrementalStrategy,
    MaterializationType,
    OnSchemaChange,
    PlanAction,
    PlanReason,
)
from sqlbuild.executor.run.helpers.incremental import execute_incremental_entry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.integration.src.sqlbuild.executor.run.incremental._test_types import (
    IncrementalFailureTestCase,
    IncrementalSuccessTestCase,
)

_STRATEGY_TO_ACTION: dict[str, PlanAction] = {
    IncrementalStrategy.APPEND: PlanAction.INCREMENTAL_APPEND,
    IncrementalStrategy.DELETE_INSERT: PlanAction.INCREMENTAL_DELETE_INSERT,
    IncrementalStrategy.MERGE: PlanAction.INCREMENTAL_MERGE,
}


def build_incremental_plan_entry(
    *,
    name: str,
    sql: str,
    target_schema: str | None,
    target_name: str,
    incremental_strategy: str,
    unique_key: tuple[str, ...] = (),
    on_schema_change: OnSchemaChange | None = None,
    cursor_column: str | None = None,
    cursor_type: str | None = None,
    cursor_grain: str | None = None,
    cursor_start: str | None = None,
    cursor_end: str | None = None,
    cursor_input_relations: tuple[tuple[str, str], ...] = (),
    cursor_inputs_model_backed: bool = False,
    type_enforcement: bool = False,
    pre_hooks: object = None,
    post_hooks: object = None,
) -> ModelPlanEntry:
    """Build a minimal ModelPlanEntry for incremental execution tests."""

    qualified: str | None = f"{target_schema}.{target_name}" if target_schema else target_name
    action: PlanAction = _STRATEGY_TO_ACTION[incremental_strategy]
    cursor_bounds: CursorBounds | None = (
        CursorBounds(start=cursor_start, end=cursor_end)
        if cursor_start is not None and cursor_end is not None
        else None
    )
    input_relations: tuple[CursorInputRelation, ...] = tuple(
        CursorInputRelation(
            relation=relation,
            cursor_column=cursor_column,
            is_model_backed=cursor_inputs_model_backed,
        )
        for relation, cursor_column in cursor_input_relations
    )
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.INCREMENTAL,
        action=action,
        reason=PlanReason.NORMAL_INCREMENTAL,
        destination=CompiledRelationDestination(
            database=None,
            schema=target_schema,
            name=target_name,
            qualified_name=qualified,
        ),
        fingerprint_query_sql=sql,
        resolved_sql=sql,
        logical_ddl="",
        incremental_strategy=incremental_strategy,
        unique_key=unique_key,
        on_schema_change=on_schema_change,
        cursor_column=cursor_column,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
        cursor_bounds=cursor_bounds,
        cursor_input_relations=input_relations,
        type_enforcement=type_enforcement,
        pre_hooks=pre_hooks,
        post_hooks=post_hooks,
    )


def build_test_audit(
    *,
    name: str,
    unresolved_sql: str,
    attached_target_name: str,
    resolved_target_name: str,
    severity: str = "warn",
    run_scope: AuditRunScope = AuditRunScope.FINAL,
) -> AuditPlanEntry:
    """Build a minimal AuditPlanEntry for incremental execution tests."""

    return AuditPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=name),
        name=name,
        resolved_sql=_resolve_audit_sql(
            unresolved_sql=unresolved_sql,
            attached_target_name=attached_target_name,
            resolved_target_name=resolved_target_name,
        ),
        unresolved_sql=unresolved_sql,
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity(severity),
        requested_run_scope=run_scope,
        effective_run_scope=run_scope,
        attached_target_name=attached_target_name,
    )


def _resolve_audit_sql(
    *, unresolved_sql: str, attached_target_name: str, resolved_target_name: str
) -> str:
    return unresolved_sql.replace(f'__ref("{attached_target_name}")', resolved_target_name)


def build_declared_columns(
    columns: tuple[tuple[str, str], ...],
) -> tuple[ColumnInfo, ...]:
    """Build ColumnInfo tuple from (name, type) pairs."""

    return tuple(ColumnInfo(name=name, type=col_type) for name, col_type in columns)


def run_success_test(
    *,
    test_case: IncrementalSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Execute a success test case and return the result."""

    result: ModelExecutionResult = _execute_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.status == ExecutionStatus.SUCCESS
    return result


def run_failure_test(
    *,
    test_case: IncrementalFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Execute a failure test case and return the result."""

    result: ModelExecutionResult = _execute_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.status == ExecutionStatus.FAILED
    return result


def verify_success_state(
    *,
    result: ModelExecutionResult,
    test_case: IncrementalSuccessTestCase,
    connection: Any,
) -> None:
    """Verify warehouse state and result for a successful incremental execution."""

    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    query_result: Any = connection.execute(f"SELECT COUNT(*) FROM {target_qualified}")
    actual_count: int = query_result.fetchone()[0]
    assert actual_count == test_case.expected_row_count
    assert len(result.audit_results) == test_case.expected_audit_count
    assert len(result.warning_messages) == test_case.expected_warning_count

    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        cursor: Any = connection.execute(query)
        actual_rows: tuple[tuple[object, ...], ...] = tuple(tuple(row) for row in cursor.fetchall())
        assert actual_rows == expected_rows, (
            f"Query: {query}\nExpected: {expected_rows}\nActual: {actual_rows}"
        )

    if test_case.expected_column_names:
        cursor = connection.execute(f"SELECT * FROM {target_qualified} LIMIT 0")
        actual_names: tuple[str, ...] = tuple(desc[0] for desc in cursor.description)
        assert actual_names == test_case.expected_column_names

    if test_case.expected_delta_cleaned:
        delta_qualified: str = _build_target_qualified(
            target_schema=test_case.target_schema,
            target_name=f"{test_case.target_name}__delta",
        )
        delta_exists: bool = _relation_exists(connection, delta_qualified)
        assert not delta_exists


def verify_failure_state(
    *,
    result: ModelExecutionResult,
    test_case: IncrementalFailureTestCase,
    connection: Any,
) -> None:
    """Verify result fields and warehouse state for a failed incremental execution."""

    assert result.failed_phase == test_case.expected_failed_phase
    assert len(result.audit_results) == test_case.expected_audit_count
    assert result.staging_relation == test_case.expected_staging_relation
    assert result.promoted_relation == test_case.expected_promoted_relation

    if test_case.expected_error_fragment is not None:
        assert result.error_message is not None
        assert test_case.expected_error_fragment in result.error_message

    if test_case.expected_row_count is not None:
        target_qualified: str = _build_target_qualified(
            target_schema=test_case.target_schema, target_name=test_case.target_name
        )
        query_result: Any = connection.execute(f"SELECT COUNT(*) FROM {target_qualified}")
        actual_count: int = query_result.fetchone()[0]
        assert actual_count == test_case.expected_row_count

    query: str
    expected_rows: tuple[tuple[object, ...], ...]
    for query, expected_rows in test_case.expected_query_results:
        cursor: Any = connection.execute(query)
        actual_rows: tuple[tuple[object, ...], ...] = tuple(tuple(row) for row in cursor.fetchall())
        assert actual_rows == expected_rows, (
            f"Query: {query}\nExpected: {expected_rows}\nActual: {actual_rows}"
        )


def _execute_test(
    *,
    test_case: IncrementalSuccessTestCase | IncrementalFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Set up and execute an incremental entry test case."""

    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    entry: ModelPlanEntry = build_incremental_plan_entry(
        name="orders",
        sql=test_case.model_sql,
        target_schema=test_case.target_schema,
        target_name=test_case.target_name,
        incremental_strategy=test_case.incremental_strategy,
        unique_key=test_case.unique_key,
        on_schema_change=test_case.on_schema_change,
        cursor_column=test_case.cursor_column,
        cursor_type=test_case.cursor_type,
        cursor_grain=test_case.cursor_grain,
        cursor_start=test_case.cursor_start,
        cursor_end=test_case.cursor_end,
        cursor_input_relations=test_case.cursor_input_relations,
        cursor_inputs_model_backed=test_case.cursor_inputs_model_backed,
        type_enforcement=test_case.type_enforcement,
        pre_hooks=test_case.pre_hook,
        post_hooks=test_case.post_hook,
    )

    declared_columns: tuple[ColumnInfo, ...] = build_declared_columns(test_case.declared_columns)
    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    model_audits: tuple[AuditPlanEntry, ...] = _build_model_audits(
        test_case=test_case,
        resolved_target_name=target_qualified,
    )
    model_targets: dict[str, CompiledRelationDestination] = {
        "orders": CompiledRelationDestination(
            database=None,
            schema=test_case.target_schema,
            name=test_case.target_name,
            qualified_name=target_qualified,
        ),
    }

    return execute_incremental_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_targets=model_targets,
        seed_targets={},
        source_map={},
        model_audits=model_audits,
        declared_columns=declared_columns,
        run_id="test_run",
        query_change_tracking=(
            test_case.query_change_tracking
            if isinstance(test_case, IncrementalSuccessTestCase)
            else True
        ),
    )


def _build_model_audits(
    *, test_case: IncrementalSuccessTestCase | IncrementalFailureTestCase, resolved_target_name: str
) -> tuple[AuditPlanEntry, ...]:
    """Build model audits from test case audit config."""

    if test_case.audit_sql is None:
        return ()
    return (
        build_test_audit(
            name="test_audit",
            unresolved_sql=test_case.audit_sql,
            attached_target_name="orders",
            resolved_target_name=resolved_target_name,
            severity=test_case.audit_severity,
            run_scope=test_case.audit_run_scope,
        ),
    )


def _build_target_qualified(*, target_schema: str | None, target_name: str) -> str:
    if target_schema:
        return f"{target_schema}.{target_name}"
    return target_name


def _relation_exists(connection: Any, qualified_name: str) -> bool:
    parts: list[str] = qualified_name.split(".")
    schema: str | None = parts[0] if len(parts) > 1 else None
    name: str = parts[-1]
    cursor: Any = connection.execute(
        "SELECT 1 FROM information_schema.tables "
        f"WHERE table_name = '{name}'" + (f" AND table_schema = '{schema}'" if schema else "")
    )
    return cursor.fetchone() is not None
