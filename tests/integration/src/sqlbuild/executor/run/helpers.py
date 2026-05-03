"""Test helpers for executor run integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.executor.run.main import execute_table_entry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.executor.run._test_types import (
    TableFailureTestCase,
    TableSuccessTestCase,
)


def build_table_plan_entry(
    *,
    name: str,
    sql: str,
    target_schema: str | None,
    target_name: str,
    type_enforcement: bool = False,
    pre_hook: object = None,
    post_hook: object = None,
) -> ModelPlanEntry:
    """Build a minimal ModelPlanEntry for table execution tests."""

    qualified: str | None = f"{target_schema}.{target_name}" if target_schema else target_name
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.FIRST_RUN,
        target=CompiledRelationTarget(
            database=None,
            schema=target_schema,
            name=target_name,
            qualified_name=qualified,
        ),
        fingerprint_query_sql=sql,
        resolved_sql=sql,
        logical_ddl=f"CREATE TABLE {qualified} AS {sql}",
        type_enforcement=type_enforcement,
        pre_hook=pre_hook,
        post_hook=post_hook,
    )


def build_test_audit_plan_entry(
    *,
    name: str,
    unresolved_sql: str,
    attached_target_name: str,
    severity: str = "warn",
) -> AuditPlanEntry:
    """Build a minimal AuditPlanEntry for execution tests."""

    return AuditPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.AUDIT, name=name),
        name=name,
        resolved_sql=unresolved_sql,
        unresolved_sql=unresolved_sql,
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity(severity),
        requested_run_scope=AuditRunScope.FINAL,
        effective_run_scope=AuditRunScope.FINAL,
        attached_target_name=attached_target_name,
    )


def build_declared_columns(
    columns: tuple[tuple[str, str], ...],
) -> tuple[ColumnInfo, ...]:
    """Build ColumnInfo tuple from (name, type) pairs."""

    return tuple(ColumnInfo(name=name, type=col_type) for name, col_type in columns)


def run_success_test(
    *,
    test_case: TableSuccessTestCase,
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
    test_case: TableFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Execute a failure test case and return the result."""

    result: ModelExecutionResult = _execute_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.status == ExecutionStatus.FAILED
    return result


def verify_success_warehouse_state(
    *,
    result: ModelExecutionResult,
    test_case: TableSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    """Verify warehouse state for a successful execution."""

    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    query_result: Any = connection.execute(f"SELECT * FROM {target_qualified}")
    rows: list[Any] = query_result.fetchall()
    assert len(rows) == test_case.expected_row_count
    assert len(result.audit_results) == test_case.expected_audit_count
    _verify_column_names(
        connection=connection, target_qualified=target_qualified, test_case=test_case
    )
    _verify_column_types(
        adapter=adapter,
        connection=connection,
        test_case=test_case,
    )
    _verify_warning_fragment(result=result, test_case=test_case)


def verify_failure_warehouse_state(
    *,
    result: ModelExecutionResult,
    test_case: TableFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    """Verify result fields and warehouse state for a failed execution."""

    assert result.failed_phase == test_case.expected_failed_phase
    assert len(result.audit_results) == test_case.expected_audit_count
    assert result.staging_relation == test_case.expected_staging_relation
    assert result.promoted_relation == test_case.expected_promoted_relation
    _verify_error_fragment(result=result, test_case=test_case)
    _verify_failure_row_count(connection=connection, test_case=test_case)


def _execute_test(
    *,
    test_case: TableSuccessTestCase | TableFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Set up and execute a table entry test case."""

    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    entry: ModelPlanEntry = build_table_plan_entry(
        name="orders",
        sql=test_case.model_sql,
        target_schema=test_case.target_schema,
        target_name=test_case.target_name,
        type_enforcement=test_case.type_enforcement,
        pre_hook=test_case.pre_hook,
        post_hook=test_case.post_hook,
    )

    model_audits: tuple[AuditPlanEntry, ...] = _build_model_audits(test_case)
    declared_columns: tuple[ColumnInfo, ...] = build_declared_columns(test_case.declared_columns)
    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    model_targets: dict[str, CompiledRelationTarget] = {
        "orders": CompiledRelationTarget(
            database=None,
            schema=test_case.target_schema,
            name=test_case.target_name,
            qualified_name=target_qualified,
        ),
    }

    return execute_table_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_targets=model_targets,
        seed_targets={},
        source_map={},
        model_audits=model_audits,
        declared_columns=declared_columns,
        promotion_mode=test_case.promotion_mode,
        run_id="test_run",
        query_change_tracking=(
            test_case.query_change_tracking if isinstance(test_case, TableSuccessTestCase) else True
        ),
    )


def _build_model_audits(
    test_case: TableSuccessTestCase | TableFailureTestCase,
) -> tuple[AuditPlanEntry, ...]:
    """Build model audits from test case audit config."""

    audits: list[AuditPlanEntry] = []
    if test_case.audit_sql is not None:
        audits.append(
            build_test_audit_plan_entry(
                name="not_null",
                unresolved_sql=test_case.audit_sql,
                attached_target_name="orders",
                severity=test_case.audit_severity,
            )
        )
    extra: tuple[str, str, str]
    for extra in test_case.extra_audits:
        audits.append(
            build_test_audit_plan_entry(
                name=extra[0],
                unresolved_sql=extra[1],
                attached_target_name="orders",
                severity=extra[2],
            )
        )
    return tuple(audits)


def _build_target_qualified(*, target_schema: str | None, target_name: str) -> str:
    if target_schema:
        return f"{target_schema}.{target_name}"
    return target_name


def _verify_column_names(
    *,
    connection: Any,
    target_qualified: str,
    test_case: TableSuccessTestCase,
) -> None:
    if not test_case.expected_column_names:
        return
    query_result: Any = connection.execute(f"SELECT * FROM {target_qualified} LIMIT 0")
    actual_names: tuple[str, ...] = tuple(desc[0] for desc in query_result.description)
    assert actual_names == test_case.expected_column_names


def _verify_column_types(
    *,
    adapter: DuckDbAdapter,
    connection: Any,
    test_case: TableSuccessTestCase,
) -> None:
    if not test_case.expected_column_types:
        return
    schema: str | None = test_case.target_schema
    columns: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection, database=None, schema=schema, name=test_case.target_name
    )
    declared_names: tuple[str, ...] = tuple(col_name for col_name, _ in test_case.declared_columns)
    enforced_types: list[str] = []
    col: ColumnInfo
    for col in columns:
        if col.name.lower() in {n.lower() for n in declared_names}:
            enforced_types.append(col.type)
    assert tuple(enforced_types) == test_case.expected_column_types


def _verify_warning_fragment(
    *,
    result: ModelExecutionResult,
    test_case: TableSuccessTestCase,
) -> None:
    if test_case.expected_warning_fragment is None:
        return
    all_warnings: str = " ".join(result.warning_messages)
    assert test_case.expected_warning_fragment in all_warnings


def _verify_error_fragment(
    *,
    result: ModelExecutionResult,
    test_case: TableFailureTestCase,
) -> None:
    if test_case.expected_error_fragment is None:
        return
    assert result.error_message is not None
    assert test_case.expected_error_fragment in result.error_message


def _verify_failure_row_count(
    *,
    connection: Any,
    test_case: TableFailureTestCase,
) -> None:
    if test_case.expected_row_count is None:
        return
    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    query_result: Any = connection.execute(f"SELECT * FROM {target_qualified}")
    rows: list[Any] = query_result.fetchall()
    assert len(rows) == test_case.expected_row_count
