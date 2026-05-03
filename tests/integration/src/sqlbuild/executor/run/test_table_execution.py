"""Integration tests for single-model table execution lifecycle."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import (
    ExecutionPhase,
    ExecutionStatus,
    TablePromotionMode,
)
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.executor.run._test_types import (
    ExecuteTableEntryTestCase,
)
from tests.integration.src.sqlbuild.executor.run.helpers import (
    execute_table_test_case,
    verify_table_test_warehouse_state,
)

STAGED_TEST_CASES: list[ExecuteTableEntryTestCase] = [
    ExecuteTableEntryTestCase(
        description="staged table creates target from query",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="staged table replaces existing target via swap",
        setup_sql=("CREATE TABLE staging.orders AS SELECT 1 AS id, 'old' AS name",),
        model_sql="SELECT 2 AS id, 'new' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="staged table with type enforcement casts columns",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        type_enforcement=True,
        declared_columns=(("id", "BIGINT"), ("name", "VARCHAR")),
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="staged table with passing audit succeeds",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
        expected_audit_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="staged table with failing error audit blocks promotion",
        setup_sql=(),
        model_sql="SELECT NULL AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_error_fragment="pre-promotion audit failed",
        expected_audit_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="staged table with failing warn audit allows promotion",
        setup_sql=(),
        model_sql="SELECT NULL AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="warn",
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
        expected_audit_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="staged CTAS failure on bad SQL returns STAGING phase error",
        setup_sql=(),
        model_sql="SELECT * FROM staging.nonexistent_table",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.STAGING,
    ),
    ExecuteTableEntryTestCase(
        description="multiple audits all run even when first errors",
        setup_sql=(),
        model_sql="SELECT NULL AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        extra_audits=(
            ("name_not_null", 'SELECT name FROM __ref("orders") WHERE name IS NULL', "error"),
        ),
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_audit_count=2,
    ),
]

DIRECT_TEST_CASES: list[ExecuteTableEntryTestCase] = [
    ExecuteTableEntryTestCase(
        description="direct table creates target from query",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.DIRECT,
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="direct table with type enforcement fails",
        setup_sql=(),
        model_sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.DIRECT,
        type_enforcement=True,
        declared_columns=(("id", "BIGINT"),),
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.TYPE_ENFORCEMENT,
        expected_error_fragment="requires staged promotion mode",
    ),
    ExecuteTableEntryTestCase(
        description="direct table with passing audit succeeds end-to-end",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.DIRECT,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
        expected_audit_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="direct failing post_hook marks model failed with promoted relation",
        setup_sql=(),
        model_sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.DIRECT,
        post_hook="THIS IS NOT VALID SQL",
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.POST_HOOK,
        expected_promoted_relation="staging.orders",
        expected_row_count=1,
    ),
]

HOOK_TEST_CASES: list[ExecuteTableEntryTestCase] = [
    ExecuteTableEntryTestCase(
        description="pre_hook runs before materialization",
        setup_sql=(),
        model_sql="SELECT * FROM staging.hook_data",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        pre_hook="CREATE TABLE staging.hook_data AS SELECT 42 AS val",
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="failing pre_hook blocks model",
        setup_sql=(),
        model_sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        pre_hook="THIS IS NOT VALID SQL",
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.PRE_HOOK,
    ),
    ExecuteTableEntryTestCase(
        description="post_hook runs after promotion",
        setup_sql=(),
        model_sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        post_hook="CREATE TABLE staging.post_hook_ran AS SELECT 1 AS marker",
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="failing post_hook marks model failed after promotion",
        setup_sql=(),
        model_sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        post_hook="THIS IS NOT VALID SQL",
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.POST_HOOK,
        expected_promoted_relation="staging.orders",
        expected_row_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="list pre_hook executes all entries in order",
        setup_sql=(),
        model_sql="SELECT * FROM staging.hook_step_2",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        pre_hook=[
            "CREATE TABLE staging.hook_step_1 AS SELECT 42 AS val",
            "CREATE TABLE staging.hook_step_2 AS SELECT * FROM staging.hook_step_1",
        ],
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
    ),
]

FAILURE_CLEANUP_TEST_CASES: list[ExecuteTableEntryTestCase] = [
    ExecuteTableEntryTestCase(
        description="staged audit failure retains staging relation",
        setup_sql=(),
        model_sql="SELECT NULL AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_staging_relation="staging.orders__staging",
        expected_audit_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="staged audit failure preserves existing target unchanged",
        setup_sql=("CREATE TABLE staging.orders AS SELECT 99 AS id, 'original' AS name",),
        model_sql="SELECT NULL AS id, 'new' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_staging_relation="staging.orders__staging",
        expected_audit_count=1,
    ),
    ExecuteTableEntryTestCase(
        description="direct failing error audit reports target already updated",
        setup_sql=(),
        model_sql="SELECT NULL AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.DIRECT,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_status=ExecutionStatus.FAILED,
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_error_fragment="target was already updated",
        expected_promoted_relation="staging.orders",
        expected_audit_count=1,
    ),
]

TYPE_ENFORCEMENT_TEST_CASES: list[ExecuteTableEntryTestCase] = [
    ExecuteTableEntryTestCase(
        description="type enforcement casts subset of columns and preserves extras",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name, 42.5 AS score",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        type_enforcement=True,
        declared_columns=(("id", "BIGINT"),),
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
        expected_column_names=("id", "name", "score"),
        expected_column_types=("BIGINT",),
    ),
    ExecuteTableEntryTestCase(
        description="type enforcement preserves produced column order",
        setup_sql=(),
        model_sql="SELECT 'alice' AS name, 1 AS id, TRUE AS active",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        type_enforcement=True,
        declared_columns=(("id", "BIGINT"), ("name", "VARCHAR")),
        expected_status=ExecutionStatus.SUCCESS,
        expected_row_count=1,
        expected_column_names=("name", "id", "active"),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    STAGED_TEST_CASES,
    ids=[case.description for case in STAGED_TEST_CASES],
)
def test_given_staged_table_entry_when_executing_then_returns_expected_result(
    test_case: ExecuteTableEntryTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = execute_table_test_case(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    verify_table_test_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    DIRECT_TEST_CASES,
    ids=[case.description for case in DIRECT_TEST_CASES],
)
def test_given_direct_table_entry_when_executing_then_returns_expected_result(
    test_case: ExecuteTableEntryTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = execute_table_test_case(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    verify_table_test_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    HOOK_TEST_CASES,
    ids=[case.description for case in HOOK_TEST_CASES],
)
def test_given_hook_config_when_executing_table_then_returns_expected_result(
    test_case: ExecuteTableEntryTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = execute_table_test_case(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    verify_table_test_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    FAILURE_CLEANUP_TEST_CASES,
    ids=[case.description for case in FAILURE_CLEANUP_TEST_CASES],
)
def test_given_failure_condition_when_executing_table_then_cleanup_matches_expected(
    test_case: ExecuteTableEntryTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = execute_table_test_case(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    assert result.failed_phase == test_case.expected_failed_phase
    assert result.staging_relation == test_case.expected_staging_relation
    verify_table_test_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    TYPE_ENFORCEMENT_TEST_CASES,
    ids=[case.description for case in TYPE_ENFORCEMENT_TEST_CASES],
)
def test_given_type_enforcement_when_executing_staged_table_then_columns_match_expected(
    test_case: ExecuteTableEntryTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = execute_table_test_case(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    verify_table_test_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ExecuteTableEntryTestCase(
            description="fingerprint failure produces warning not failure",
            setup_sql=(),
            model_sql="SELECT 1 AS id",
            target_schema="staging",
            target_name="orders",
            promotion_mode=TablePromotionMode.STAGED,
            expected_status=ExecutionStatus.SUCCESS,
            expected_row_count=1,
            fingerprint_schema="nonexistent_schema",
            expected_warning_fragment="fingerprint write failed",
        ),
    ],
    ids=["fingerprint failure produces warning not failure"],
)
def test_given_fingerprint_failure_when_executing_table_then_succeeds_with_warning(
    test_case: ExecuteTableEntryTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = execute_table_test_case(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.status == test_case.expected_status
    verify_table_test_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )
