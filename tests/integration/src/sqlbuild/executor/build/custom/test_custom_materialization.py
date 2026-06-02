"""Integration tests for custom materialization executor lifecycle."""

from __future__ import annotations

from typing import Any

import duckdb
import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.executor.custom.models import MaterializationContext, MaterializationResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from tests.integration.src.sqlbuild.executor.build.custom._test_types import (
    CleanupTestCase,
    ContextVerificationTestCase,
    CustomFailureTestCase,
    CustomSuccessTestCase,
    FrameworkAuditTestCase,
    HookTestCase,
    UserAuditTestCase,
)
from tests.integration.src.sqlbuild.executor.build.custom.helpers import (
    build_cleanup_fn,
    build_custom_plan_entry,
    build_failing_audit,
    build_passing_audit,
    build_simple_fn,
    build_user_audit_fn,
    relation_exists,
    resolve_fn,
    row_count,
    run_custom_entry,
)

SUCCESS_TEST_CASES: list[CustomSuccessTestCase] = [
    CustomSuccessTestCase(
        description="simple table creation via custom materialization",
        model_sql="SELECT 1 AS id, 'alice' AS name UNION ALL SELECT 2, 'bob'",
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=2,
        fn_name="simple",
    ),
    CustomSuccessTestCase(
        description="staging with cleanup via custom materialization",
        model_sql="SELECT 1 AS id, 'alice' AS name",
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
        fn_name="staging",
    ),
    CustomSuccessTestCase(
        description="user runs audits and returns results",
        model_sql="SELECT 1 AS id, 'alice' AS name",
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
        fn_name="audit_running",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SUCCESS_TEST_CASES,
    ids=[case.description for case in SUCCESS_TEST_CASES],
)
def test_given_custom_materialization_when_executing_then_succeeds(
    test_case: CustomSuccessTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    entry: ModelPlanEntry = build_custom_plan_entry(sql=test_case.model_sql)

    result: ModelExecutionResult = run_custom_entry(
        adapter=adapter,
        connection=connection,
        entry=entry,
        materialize_fn=resolve_fn(test_case.fn_name),
    )

    assert result.status == test_case.expected_status
    assert row_count(connection, qualified_name="main.test_model") == test_case.expected_row_count


FAILURE_TEST_CASES: list[CustomFailureTestCase] = [
    CustomFailureTestCase(
        description="user returns failed with error message",
        model_sql="SELECT 1 AS id",
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
        expected_error_fragment="user-reported failure",
        fn_name="failing",
    ),
    CustomFailureTestCase(
        description="user function raises exception",
        model_sql="SELECT 1 AS id",
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.CUSTOM_MATERIALIZATION,
        expected_error_fragment="materialization crashed",
        fn_name="excepting",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    FAILURE_TEST_CASES,
    ids=[case.description for case in FAILURE_TEST_CASES],
)
def test_given_custom_materialization_when_failing_then_reports_failure(
    test_case: CustomFailureTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    entry: ModelPlanEntry = build_custom_plan_entry(sql=test_case.model_sql)

    result: ModelExecutionResult = run_custom_entry(
        adapter=adapter,
        connection=connection,
        entry=entry,
        materialize_fn=resolve_fn(test_case.fn_name),
    )

    assert result.status == test_case.expected_status
    assert result.failed_phase == test_case.expected_failed_phase
    assert result.error_message is not None
    assert test_case.expected_error_fragment in result.error_message


HOOK_TEST_CASES: list[HookTestCase] = [
    HookTestCase(
        description="pre_hook executes before materialization",
        pre_hook="CREATE TABLE main.hook_marker (x INT); INSERT INTO main.hook_marker VALUES (1)",
        post_hook=None,
        expected_status=ExecutionStatus.SUCCESS,
        expected_table_exists=True,
    ),
    HookTestCase(
        description="post_hook executes after materialization",
        pre_hook=None,
        post_hook="CREATE TABLE main.hook_marker (x INT); INSERT INTO main.hook_marker VALUES (2)",
        expected_status=ExecutionStatus.SUCCESS,
        expected_table_exists=True,
    ),
    HookTestCase(
        description="pre_hook failure skips materialization",
        pre_hook="SELECT * FROM nonexistent_table_for_hook",
        post_hook=None,
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.PRE_HOOK,
        expected_table_exists=False,
    ),
    HookTestCase(
        description="post_hook failure after successful materialization",
        pre_hook=None,
        post_hook="SELECT * FROM nonexistent_table_for_hook",
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.POST_HOOK,
        expected_table_exists=True,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    HOOK_TEST_CASES,
    ids=[case.description for case in HOOK_TEST_CASES],
)
def test_given_custom_materialization_with_hooks_when_executing_then_handles_hooks(
    test_case: HookTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    entry: ModelPlanEntry = build_custom_plan_entry(
        sql="SELECT 1 AS id",
        pre_hook=test_case.pre_hook,
        post_hook=test_case.post_hook,
    )

    result: ModelExecutionResult = run_custom_entry(
        adapter=adapter, connection=connection, entry=entry, materialize_fn=build_simple_fn()
    )

    assert result.status == test_case.expected_status
    assert result.failed_phase == test_case.expected_failed_phase
    assert (
        relation_exists(connection, schema="main", name="test_model")
        == test_case.expected_table_exists
    )


FRAMEWORK_AUDIT_TEST_CASES: list[FrameworkAuditTestCase] = [
    FrameworkAuditTestCase(
        description="framework runs passing audit when user does not call run_audits",
        audit_passes=True,
        expected_status=ExecutionStatus.SUCCESS,
        expected_audit_count=1,
    ),
    FrameworkAuditTestCase(
        description="framework audit error blocks post_hook",
        audit_passes=False,
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_audit_count=1,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    FRAMEWORK_AUDIT_TEST_CASES,
    ids=[case.description for case in FRAMEWORK_AUDIT_TEST_CASES],
)
def test_given_custom_materialization_when_framework_runs_audits_then_handles_outcome(
    test_case: FrameworkAuditTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    entry: ModelPlanEntry = build_custom_plan_entry(sql="SELECT 1 AS id")
    model_targets: dict[str, CompiledRelationDestination] = {"test_model": entry.destination}
    audit: AuditPlanEntry = (
        build_passing_audit(name="check_empty", target_name="test_model")
        if test_case.audit_passes
        else build_failing_audit(name="check_rows", target_name="test_model")
    )

    result: ModelExecutionResult = run_custom_entry(
        adapter=adapter,
        connection=connection,
        entry=entry,
        materialize_fn=build_user_audit_fn(expect_pass=test_case.audit_passes),
        model_audits=(audit,),
        model_targets=model_targets,
    )
    actual_audit: AuditPlanEntry = (
        build_passing_audit(name="check_empty", target_name="test_model")
        if test_case.audit_passes
        else build_failing_audit(name="check_rows", target_name="test_model")
    )

    result: ModelExecutionResult = run_custom_entry(
        adapter=adapter,
        connection=connection,
        entry=entry,
        materialize_fn=build_simple_fn(),
        model_audits=(actual_audit,),
        model_targets=model_targets,
    )

    assert result.status == test_case.expected_status
    assert result.failed_phase == test_case.expected_failed_phase
    assert len(result.audit_results) == test_case.expected_audit_count


USER_AUDIT_TEST_CASES: list[UserAuditTestCase] = [
    UserAuditTestCase(
        description="user calls run_audits with passing audit against staging",
        audit_passes=True,
        expected_status=ExecutionStatus.SUCCESS,
        expected_audit_count=1,
        expected_audit_outcome=AuditOutcome.PASS,
    ),
    UserAuditTestCase(
        description="user calls run_audits with failing audit and returns failed",
        audit_passes=False,
        expected_status=ExecutionStatus.FAILED,
        expected_audit_count=1,
        expected_audit_outcome=AuditOutcome.ERROR,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    USER_AUDIT_TEST_CASES,
    ids=[case.description for case in USER_AUDIT_TEST_CASES],
)
def test_given_custom_materialization_when_user_runs_audits_then_handles_outcome(
    test_case: UserAuditTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    entry: ModelPlanEntry = build_custom_plan_entry(sql="SELECT 1 AS id")
    model_targets: dict[str, CompiledRelationDestination] = {"test_model": entry.destination}
    actual_audit: AuditPlanEntry = (
        build_passing_audit(name="check_empty", target_name="test_model")
        if test_case.audit_passes
        else build_failing_audit(name="check_rows", target_name="test_model")
    )

    result: ModelExecutionResult = run_custom_entry(
        adapter=adapter,
        connection=connection,
        entry=entry,
        materialize_fn=build_user_audit_fn(expect_pass=test_case.audit_passes),
        model_audits=(actual_audit,),
        model_targets=model_targets,
    )

    assert result.status == test_case.expected_status
    assert len(result.audit_results) == test_case.expected_audit_count
    assert result.audit_results[0].outcome == test_case.expected_audit_outcome


CLEANUP_TEST_CASES: list[CleanupTestCase] = [
    CleanupTestCase(
        description="cleanup relations dropped on success",
        user_fails=False,
        expected_staging_exists=False,
    ),
    CleanupTestCase(
        description="cleanup relations kept on failure",
        user_fails=True,
        expected_staging_exists=True,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CLEANUP_TEST_CASES,
    ids=[case.description for case in CLEANUP_TEST_CASES],
)
def test_given_custom_materialization_with_cleanup_when_completing_then_handles_cleanup(
    test_case: CleanupTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    entry: ModelPlanEntry = build_custom_plan_entry(sql="SELECT 1 AS id")

    run_custom_entry(
        adapter=adapter,
        connection=connection,
        entry=entry,
        materialize_fn=build_cleanup_fn(fail=test_case.user_fails),
    )

    assert (
        relation_exists(connection, schema="main", name="test_model__staging")
        == test_case.expected_staging_exists
    )


CONTEXT_TEST_CASES: list[ContextVerificationTestCase] = [
    ContextVerificationTestCase(
        description="context fields populated for first run with full refresh",
        reason=PlanReason.FULL_REFRESH,
        custom_config={"tracking_schema": "meta"},
        custom_placeholders={"start": "'2020-01-01'"},
        target="prod",
        effective_vars={"user": "kevin"},
        expected_is_first_run=True,
        expected_is_full_refresh=True,
        expected_query_changed=False,
        expected_config_key="tracking_schema",
        expected_config_value="meta",
        expected_placeholder_key="start",
        expected_placeholder_value="'2020-01-01'",
        expected_target="prod",
        expected_var_key="user",
        expected_var_value="kevin",
        expected_qualified_name="meta.partition_state",
        expected_destination_schema_qualified_name="main.partition_state",
        expected_preserved_qualified_name="external.partition_state",
    ),
    ContextVerificationTestCase(
        description="context fields populated for query changed run",
        reason=PlanReason.QUERY_CHANGED,
        custom_config={"mode": "incremental"},
        custom_placeholders={},
        target="dev",
        effective_vars={"schema_prefix": "staging"},
        expected_is_first_run=True,
        expected_is_full_refresh=False,
        expected_query_changed=True,
        expected_config_key="mode",
        expected_config_value="incremental",
        expected_placeholder_key="",
        expected_placeholder_value="",
        expected_target="dev",
        expected_var_key="schema_prefix",
        expected_var_value="staging",
        expected_qualified_name="meta.partition_state",
        expected_destination_schema_qualified_name="main.partition_state",
        expected_preserved_qualified_name="external.partition_state",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CONTEXT_TEST_CASES,
    ids=[case.description for case in CONTEXT_TEST_CASES],
)
def test_given_custom_materialization_when_executing_then_context_fields_populated(
    test_case: ContextVerificationTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: duckdb.DuckDBPyConnection = duckdb.connect(":memory:")
    entry: ModelPlanEntry = build_custom_plan_entry(
        sql="SELECT 1 AS id",
        reason=test_case.reason,
        custom_config=test_case.custom_config,
        custom_placeholders=test_case.custom_placeholders,
    )

    captured: dict[str, Any] = {}

    def materialize(ctx: MaterializationContext) -> MaterializationResult:
        captured["is_first_run"] = ctx.is_first_run
        captured["is_full_refresh"] = ctx.is_full_refresh
        captured["query_changed"] = ctx.query_changed
        captured["config"] = ctx.config
        captured["placeholders"] = ctx.placeholders
        captured["relation"] = ctx.destination
        captured["target"] = ctx.build_target
        captured["vars"] = ctx.vars
        captured["qualified_name"] = ctx.qualify_name(
            "partition_state", schema="meta", database=None
        )
        captured["destination_schema_qualified_name"] = ctx.qualify_in_destination_schema(
            "partition_state"
        )
        captured["preserved_qualified_name"] = ctx.qualify_in_destination_schema(
            "external.partition_state"
        )
        ctx.adapter.create_table_as(
            ctx.connection,
            target=ctx.destination,
            sql=ctx.sql,
            statement_recorder=ctx.statement_recorder,
        )
        return MaterializationResult(relation=ctx.destination)

    run_custom_entry(
        adapter=adapter,
        connection=connection,
        entry=entry,
        materialize_fn=materialize,
        target=test_case.target,
        effective_vars=test_case.effective_vars,
    )

    assert captured["is_first_run"] == test_case.expected_is_first_run
    assert captured["is_full_refresh"] == test_case.expected_is_full_refresh
    assert captured["query_changed"] == test_case.expected_query_changed
    assert captured["config"][test_case.expected_config_key] == test_case.expected_config_value
    assert captured["target"] == test_case.expected_target
    assert captured["relation"] == "main.test_model"
    assert captured["vars"][test_case.expected_var_key] == test_case.expected_var_value
    assert captured["qualified_name"] == test_case.expected_qualified_name
    assert (
        captured["destination_schema_qualified_name"]
        == test_case.expected_destination_schema_qualified_name
    )
    assert captured["preserved_qualified_name"] == test_case.expected_preserved_qualified_name
