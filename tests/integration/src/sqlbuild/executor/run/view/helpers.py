"""Test helpers for view executor integration tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationTarget,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.executor.run.helpers.view import execute_view_entry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.executor.run.view._test_types import (
    ViewFailureTestCase,
    ViewSuccessTestCase,
)


def build_view_plan_entry(
    *,
    name: str,
    sql: str,
    target_schema: str | None,
    target_name: str,
    pre_hook: object = None,
    post_hook: object = None,
) -> ModelPlanEntry:
    """Build a minimal ModelPlanEntry for view execution tests."""

    qualified: str | None = f"{target_schema}.{target_name}" if target_schema else target_name
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.VIEW,
        action=PlanAction.CREATE_VIEW,
        reason=PlanReason.FIRST_RUN,
        target=CompiledRelationTarget(
            database=None,
            schema=target_schema,
            name=target_name,
            qualified_name=qualified,
        ),
        fingerprint_query_sql=sql,
        resolved_sql=sql,
        logical_ddl=f"CREATE OR REPLACE VIEW {qualified} AS {sql}",
        pre_hook=pre_hook,
        post_hook=post_hook,
    )


def build_view_audit_plan_entry(
    *,
    name: str,
    unresolved_sql: str,
    attached_target_name: str,
    severity: str = "warn",
) -> AuditPlanEntry:
    """Build a minimal AuditPlanEntry for view execution tests."""

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


def run_view_success_test(
    *,
    test_case: ViewSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Execute a view success test case and return the result."""

    result: ModelExecutionResult = _execute_view_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.status == ExecutionStatus.SUCCESS
    return result


def run_view_failure_test(
    *,
    test_case: ViewFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Execute a view failure test case and return the result."""

    result: ModelExecutionResult = _execute_view_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.status == ExecutionStatus.FAILED
    return result


def verify_view_success_state(
    *,
    result: ModelExecutionResult,
    test_case: ViewSuccessTestCase,
    connection: Any,
) -> None:
    """Verify warehouse state for a successful view execution."""

    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    query_result: Any = connection.execute(f"SELECT * FROM {target_qualified}")
    rows: list[Any] = query_result.fetchall()
    assert len(rows) == test_case.expected_row_count
    assert len(result.audit_results) == test_case.expected_audit_count
    _verify_warning_fragment(result=result, test_case=test_case)


def verify_view_failure_state(
    *,
    result: ModelExecutionResult,
    test_case: ViewFailureTestCase,
) -> None:
    """Verify result fields for a failed view execution."""

    assert result.failed_phase == test_case.expected_failed_phase
    assert len(result.audit_results) == test_case.expected_audit_count
    assert result.promoted_relation == test_case.expected_promoted_relation
    _verify_error_fragment(result=result, test_case=test_case)


def _execute_view_test(
    *,
    test_case: ViewSuccessTestCase | ViewFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> ModelExecutionResult:
    """Set up and execute a view entry test case."""

    sql: str
    for sql in test_case.setup_sql:
        connection.execute(sql)

    entry: ModelPlanEntry = build_view_plan_entry(
        name="dim_view",
        sql=test_case.model_sql,
        target_schema=test_case.target_schema,
        target_name=test_case.target_name,
        pre_hook=test_case.pre_hook,
        post_hook=test_case.post_hook,
    )

    model_audits: tuple[AuditPlanEntry, ...] = _build_model_audits(test_case)
    target_qualified: str = _build_target_qualified(
        target_schema=test_case.target_schema, target_name=test_case.target_name
    )
    model_targets: dict[str, CompiledRelationTarget] = {
        "dim_view": CompiledRelationTarget(
            database=None,
            schema=test_case.target_schema,
            name=test_case.target_name,
            qualified_name=target_qualified,
        ),
    }

    return execute_view_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_targets=model_targets,
        seed_targets={},
        source_map={},
        model_audits=model_audits,
        run_id="test_run",
        query_change_tracking=(
            test_case.query_change_tracking if isinstance(test_case, ViewSuccessTestCase) else True
        ),
    )


def _build_model_audits(
    test_case: ViewSuccessTestCase | ViewFailureTestCase,
) -> tuple[AuditPlanEntry, ...]:
    """Build model audits from test case audit config."""

    audits: list[AuditPlanEntry] = []
    if test_case.audit_sql is not None:
        audits.append(
            build_view_audit_plan_entry(
                name="not_null",
                unresolved_sql=test_case.audit_sql,
                attached_target_name="dim_view",
                severity=test_case.audit_severity,
            )
        )
    extra: tuple[str, str, str]
    for extra in test_case.extra_audits:
        audits.append(
            build_view_audit_plan_entry(
                name=extra[0],
                unresolved_sql=extra[1],
                attached_target_name="dim_view",
                severity=extra[2],
            )
        )
    return tuple(audits)


def _build_target_qualified(*, target_schema: str | None, target_name: str) -> str:
    if target_schema:
        return f"{target_schema}.{target_name}"
    return target_name


def _verify_warning_fragment(
    *,
    result: ModelExecutionResult,
    test_case: ViewSuccessTestCase,
) -> None:
    if test_case.expected_warning_fragment is None:
        return
    all_warnings: str = " ".join(result.warning_messages)
    assert test_case.expected_warning_fragment in all_warnings


def _verify_error_fragment(
    *,
    result: ModelExecutionResult,
    test_case: ViewFailureTestCase,
) -> None:
    if test_case.expected_error_fragment is None:
        return
    assert result.error_message is not None
    assert test_case.expected_error_fragment in result.error_message
