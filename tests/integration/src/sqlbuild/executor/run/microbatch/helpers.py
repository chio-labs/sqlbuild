"""Test helpers for microbatch executor integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationDestination,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
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
    IncrementalMode,
    IncrementalStrategy,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.executor.run.helpers.microbatch import execute_microbatch_entry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.integration.src.sqlbuild.executor.run.microbatch._test_types import (
    MicrobatchFailureTestCase,
    MicrobatchSuccessTestCase,
)

_STRATEGY_TO_ACTION: dict[str, PlanAction] = {
    IncrementalStrategy.APPEND: PlanAction.INCREMENTAL_APPEND,
    IncrementalStrategy.DELETE_INSERT: PlanAction.INCREMENTAL_DELETE_INSERT,
    IncrementalStrategy.MERGE: PlanAction.INCREMENTAL_MERGE,
}


def build_microbatch_plan_entry(
    *,
    test_case: MicrobatchSuccessTestCase | MicrobatchFailureTestCase,
) -> ModelPlanEntry:
    """Build a ModelPlanEntry for microbatch execution tests."""

    target_schema: str | None = test_case.target_schema
    target_name: str = test_case.target_name
    qualified: str | None = f"{target_schema}.{target_name}" if target_schema else target_name
    action: PlanAction = _STRATEGY_TO_ACTION[test_case.incremental_strategy]
    reason: PlanReason = PlanReason.NORMAL_INCREMENTAL
    if test_case.is_full_refresh:
        action = PlanAction.CREATE_TABLE
        reason = PlanReason.FULL_REFRESH

    microbatch_range: CursorBounds | None = (
        CursorBounds(
            start=test_case.microbatch_start,
            end=test_case.microbatch_end,
        )
        if not test_case.is_full_refresh and test_case.use_plan_microbatch_range
        else None
    )
    cursor_input_relations: tuple[CursorInputRelation, ...] = tuple(
        CursorInputRelation(
            relation=relation,
            cursor_column=cursor_column,
            is_model_backed=test_case.cursor_inputs_model_backed,
        )
        for relation, cursor_column in test_case.cursor_input_relations
    )

    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
        name="orders",
        relative_path=Path("models/orders.sql"),
        materialization_type=MaterializationType.INCREMENTAL,
        action=action,
        reason=reason,
        target=CompiledRelationDestination(
            database=None,
            schema=target_schema,
            name=target_name,
            qualified_name=qualified,
        ),
        fingerprint_query_sql=test_case.model_sql,
        resolved_sql=test_case.model_sql,
        logical_ddl="",
        incremental_strategy=test_case.incremental_strategy,
        incremental_mode=IncrementalMode.MICROBATCH,
        cursor_column=test_case.cursor_column,
        cursor_type=test_case.cursor_type,
        cursor_grain=test_case.cursor_grain,
        cursor_bounds=CursorBounds(start=MICROBATCH_START_SENTINEL, end=MICROBATCH_END_SENTINEL),
        cursor_input_relations=cursor_input_relations,
        batch_size=test_case.batch_size,
        microbatch_range=microbatch_range,
        unique_key=test_case.unique_key,
        on_schema_change=test_case.on_schema_change,
        pre_hook=test_case.pre_hook,
        post_hook=test_case.post_hook,
    )


def run_success_test(
    *,
    test_case: MicrobatchSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Execute a microbatch success test case and return the result."""

    result: ModelExecutionResult = _execute_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.status == ExecutionStatus.SUCCESS
    return result


def run_failure_test(
    *,
    test_case: MicrobatchFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Execute a microbatch failure test case and return the result."""

    result: ModelExecutionResult = _execute_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.status == ExecutionStatus.FAILED
    return result


def verify_success_state(
    *,
    result: ModelExecutionResult,
    test_case: MicrobatchSuccessTestCase,
    connection: Any,
) -> None:
    """Verify warehouse state and result for a successful microbatch execution."""

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
        assert not _relation_exists(connection, delta_qualified)

    statement_output: str = "\n".join(e.content for e in result.lifecycle_events)
    expected_fragment: str
    for expected_fragment in test_case.expected_executed_statement_fragments:
        assert expected_fragment in statement_output


def verify_failure_state(
    *,
    result: ModelExecutionResult,
    test_case: MicrobatchFailureTestCase,
    connection: Any,
) -> None:
    """Verify result fields and warehouse state for a failed microbatch execution."""

    assert result.failed_phase == test_case.expected_failed_phase
    assert len(result.audit_results) == test_case.expected_audit_count

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

    if test_case.expected_delta_retained:
        delta_qualified: str = _build_target_qualified(
            target_schema=test_case.target_schema,
            target_name=f"{test_case.target_name}__delta",
        )
        assert _relation_exists(connection, delta_qualified)


def _execute_test(
    *,
    test_case: MicrobatchSuccessTestCase | MicrobatchFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Set up and execute a microbatch test case."""

    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    entry: ModelPlanEntry = build_microbatch_plan_entry(test_case=test_case)
    model_audits: tuple[AuditPlanEntry, ...] = _build_model_audits(test_case)
    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    model_targets: dict[str, CompiledRelationDestination] = {
        "orders": CompiledRelationDestination(
            database=None,
            schema=test_case.target_schema,
            name=test_case.target_name,
            qualified_name=target_qualified,
        ),
    }

    return execute_microbatch_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_targets=model_targets,
        seed_targets={},
        source_map={},
        model_audits=model_audits,
        declared_columns=(),
        run_id="test_run",
        query_change_tracking=(
            test_case.query_change_tracking
            if isinstance(test_case, MicrobatchSuccessTestCase)
            else True
        ),
        is_full_refresh=test_case.is_full_refresh,
    )


def _build_model_audits(
    test_case: MicrobatchSuccessTestCase | MicrobatchFailureTestCase,
) -> tuple[AuditPlanEntry, ...]:
    """Build model audits from test case audit config."""

    if test_case.audit_sql is None:
        return ()
    resolved_target_name: str = _build_target_qualified(
        target_schema=test_case.target_schema,
        target_name=test_case.target_name,
    )
    return (
        AuditPlanEntry(
            key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name="test_audit"),
            name="test_audit",
            resolved_sql=test_case.audit_sql.replace('__ref("orders")', resolved_target_name),
            unresolved_sql=test_case.audit_sql,
            attachment_kind=AuditAttachmentKind.MODEL,
            severity=AuditSeverity(test_case.audit_severity),
            requested_run_scope=test_case.audit_run_scope,
            effective_run_scope=test_case.audit_run_scope,
            attached_target_name="orders",
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
