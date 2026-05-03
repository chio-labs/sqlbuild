"""Integration tests for single-model table execution lifecycle."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import (
    ExecutionPhase,
    TablePromotionMode,
)
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.executor.run._test_types import (
    TableFailureTestCase,
    TableSuccessTestCase,
)
from tests.integration.src.sqlbuild.executor.run.helpers import (
    run_failure_test,
    run_success_test,
    verify_failure_warehouse_state,
    verify_success_warehouse_state,
)

STAGED_SUCCESS_TEST_CASES: list[TableSuccessTestCase] = [
    TableSuccessTestCase(
        description="staged table creates target from query",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        expected_row_count=1,
    ),
    TableSuccessTestCase(
        description="staged table replaces existing target via swap",
        setup_sql=("CREATE TABLE staging.orders AS SELECT 1 AS id, 'old' AS name",),
        model_sql="SELECT 2 AS id, 'new' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        expected_row_count=1,
    ),
    TableSuccessTestCase(
        description="staged table with type enforcement casts columns",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        type_enforcement=True,
        declared_columns=(("id", "BIGINT"), ("name", "VARCHAR")),
        expected_row_count=1,
    ),
    TableSuccessTestCase(
        description="staged table with passing audit succeeds",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_row_count=1,
        expected_audit_count=1,
    ),
    TableSuccessTestCase(
        description="staged table with failing warn audit allows promotion",
        setup_sql=(),
        model_sql="SELECT NULL AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="warn",
        expected_row_count=1,
        expected_audit_count=1,
    ),
]

STAGED_FAILURE_TEST_CASES: list[TableFailureTestCase] = [
    TableFailureTestCase(
        description="staged table with failing error audit blocks promotion",
        setup_sql=(),
        model_sql="SELECT NULL AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_error_fragment="final audit for 'orders' failed before replacing target table",
        expected_staging_relation="staging.orders__staging",
        expected_audit_count=1,
    ),
    TableFailureTestCase(
        description="staged CTAS failure on bad SQL returns STAGING phase error",
        setup_sql=(),
        model_sql="SELECT * FROM staging.nonexistent_table",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        expected_failed_phase=ExecutionPhase.STAGING,
        expected_staging_relation="staging.orders__staging",
    ),
    TableFailureTestCase(
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
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_staging_relation="staging.orders__staging",
        expected_audit_count=2,
    ),
]

DIRECT_SUCCESS_TEST_CASES: list[TableSuccessTestCase] = [
    TableSuccessTestCase(
        description="direct table creates target from query",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.DIRECT,
        expected_row_count=1,
    ),
    TableSuccessTestCase(
        description="direct table with passing audit succeeds end-to-end",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.DIRECT,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_row_count=1,
        expected_audit_count=1,
    ),
]

DIRECT_FAILURE_TEST_CASES: list[TableFailureTestCase] = [
    TableFailureTestCase(
        description="direct table with type enforcement fails",
        setup_sql=(),
        model_sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.DIRECT,
        type_enforcement=True,
        declared_columns=(("id", "BIGINT"),),
        expected_failed_phase=ExecutionPhase.TYPE_ENFORCEMENT,
        expected_error_fragment="requires staged promotion mode",
    ),
    TableFailureTestCase(
        description="direct failing post_hook marks model failed with promoted relation",
        setup_sql=(),
        model_sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.DIRECT,
        post_hook="THIS IS NOT VALID SQL",
        expected_failed_phase=ExecutionPhase.POST_HOOK,
        expected_promoted_relation="staging.orders",
        expected_row_count=1,
    ),
    TableFailureTestCase(
        description="direct failing error audit reports target already updated",
        setup_sql=(),
        model_sql="SELECT NULL AS id, 'alice' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.DIRECT,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_error_fragment="final audit for 'orders' failed after target table was replaced",
        expected_promoted_relation="staging.orders",
        expected_audit_count=1,
    ),
]

HOOK_SUCCESS_TEST_CASES: list[TableSuccessTestCase] = [
    TableSuccessTestCase(
        description="pre_hook runs before materialization",
        setup_sql=(),
        model_sql="SELECT * FROM staging.hook_data",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        pre_hook="CREATE TABLE staging.hook_data AS SELECT 42 AS val",
        expected_row_count=1,
    ),
    TableSuccessTestCase(
        description="post_hook runs after promotion",
        setup_sql=(),
        model_sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        post_hook="CREATE TABLE staging.post_hook_ran AS SELECT 1 AS marker",
        expected_row_count=1,
    ),
    TableSuccessTestCase(
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
        expected_row_count=1,
    ),
]

HOOK_FAILURE_TEST_CASES: list[TableFailureTestCase] = [
    TableFailureTestCase(
        description="failing pre_hook blocks model",
        setup_sql=(),
        model_sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        pre_hook="THIS IS NOT VALID SQL",
        expected_failed_phase=ExecutionPhase.PRE_HOOK,
    ),
    TableFailureTestCase(
        description="failing post_hook marks model failed after promotion",
        setup_sql=(),
        model_sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        post_hook="THIS IS NOT VALID SQL",
        expected_failed_phase=ExecutionPhase.POST_HOOK,
        expected_promoted_relation="staging.orders",
        expected_row_count=1,
    ),
]

CLEANUP_FAILURE_TEST_CASES: list[TableFailureTestCase] = [
    TableFailureTestCase(
        description="staged audit failure retains staging relation",
        setup_sql=(),
        model_sql="SELECT NULL AS id",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_staging_relation="staging.orders__staging",
        expected_audit_count=1,
    ),
    TableFailureTestCase(
        description="staged audit failure preserves existing target unchanged",
        setup_sql=("CREATE TABLE staging.orders AS SELECT 99 AS id, 'original' AS name",),
        model_sql="SELECT NULL AS id, 'new' AS name",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        audit_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        audit_severity="error",
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_staging_relation="staging.orders__staging",
        expected_audit_count=1,
    ),
]

TYPE_ENFORCEMENT_TEST_CASES: list[TableSuccessTestCase] = [
    TableSuccessTestCase(
        description="type enforcement casts subset of columns and preserves extras",
        setup_sql=(),
        model_sql="SELECT 1 AS id, 'alice' AS name, 42.5 AS score",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        type_enforcement=True,
        declared_columns=(("id", "BIGINT"),),
        expected_row_count=1,
        expected_column_names=("id", "name", "score"),
        expected_column_types=("BIGINT",),
    ),
    TableSuccessTestCase(
        description="type enforcement preserves produced column order",
        setup_sql=(),
        model_sql="SELECT 'alice' AS name, 1 AS id, TRUE AS active",
        target_schema="staging",
        target_name="orders",
        promotion_mode=TablePromotionMode.STAGED,
        type_enforcement=True,
        declared_columns=(("id", "BIGINT"), ("name", "VARCHAR")),
        expected_row_count=1,
        expected_column_names=("name", "id", "active"),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    STAGED_SUCCESS_TEST_CASES,
    ids=[case.description for case in STAGED_SUCCESS_TEST_CASES],
)
def test_given_staged_table_when_executing_then_succeeds(
    test_case: TableSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_success_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert len(result.audit_results) == test_case.expected_audit_count
    verify_success_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    STAGED_FAILURE_TEST_CASES,
    ids=[case.description for case in STAGED_FAILURE_TEST_CASES],
)
def test_given_staged_table_when_executing_then_fails(
    test_case: TableFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_failure_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.failed_phase == test_case.expected_failed_phase
    verify_failure_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    DIRECT_SUCCESS_TEST_CASES,
    ids=[case.description for case in DIRECT_SUCCESS_TEST_CASES],
)
def test_given_direct_table_when_executing_then_succeeds(
    test_case: TableSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_success_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert len(result.audit_results) == test_case.expected_audit_count
    verify_success_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    DIRECT_FAILURE_TEST_CASES,
    ids=[case.description for case in DIRECT_FAILURE_TEST_CASES],
)
def test_given_direct_table_when_executing_then_fails(
    test_case: TableFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_failure_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.failed_phase == test_case.expected_failed_phase
    verify_failure_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    HOOK_SUCCESS_TEST_CASES,
    ids=[case.description for case in HOOK_SUCCESS_TEST_CASES],
)
def test_given_hook_config_when_executing_table_then_succeeds(
    test_case: TableSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_success_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert len(result.audit_results) == test_case.expected_audit_count
    verify_success_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    HOOK_FAILURE_TEST_CASES,
    ids=[case.description for case in HOOK_FAILURE_TEST_CASES],
)
def test_given_hook_config_when_executing_table_then_fails(
    test_case: TableFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_failure_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.failed_phase == test_case.expected_failed_phase
    verify_failure_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    CLEANUP_FAILURE_TEST_CASES,
    ids=[case.description for case in CLEANUP_FAILURE_TEST_CASES],
)
def test_given_failure_condition_when_executing_table_then_cleanup_matches(
    test_case: TableFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_failure_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert result.staging_relation == test_case.expected_staging_relation
    verify_failure_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    TYPE_ENFORCEMENT_TEST_CASES,
    ids=[case.description for case in TYPE_ENFORCEMENT_TEST_CASES],
)
def test_given_type_enforcement_when_executing_staged_table_then_columns_match(
    test_case: TableSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_success_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert len(result.audit_results) == test_case.expected_audit_count
    verify_success_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TableSuccessTestCase(
            description="missing target schema warns when query tracking is enabled",
            setup_sql=(),
            model_sql="SELECT 1 AS id",
            target_schema=None,
            target_name="orders",
            promotion_mode=TablePromotionMode.STAGED,
            expected_row_count=1,
            expected_warning_fragment="target schema is missing",
        ),
    ],
    ids=["missing target schema warns when query tracking is enabled"],
)
def test_given_fingerprint_failure_when_executing_table_then_succeeds_with_warning(
    test_case: TableSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_success_test(
        test_case=test_case, adapter=adapter, connection=connection
    )

    assert len(result.audit_results) == test_case.expected_audit_count
    verify_success_warehouse_state(
        result=result, test_case=test_case, adapter=adapter, connection=connection
    )
