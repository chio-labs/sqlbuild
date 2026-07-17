"""Integration tests for single-model table execution lifecycle."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction, PythonHookEntry, SqlHookEntry
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.executor.run.main._execute import execute_table_entry
from sqlbuild.executor.run.models import ModelExecutionResult, ModelMaterializationContext
from sqlbuild.executor.run.types import ExecutionPhase
from sqlbuild.executor.scheduling.types import ExecutionStatus
from tests.integration.src.sqlbuild.executor.run._test_types import (
    TableFailureTestCase,
    TableReuseAuditProofExecutionTestCase,
    TableReuseExecutionTestCase,
    TableReuseFailureExecutionTestCase,
    TableSuccessTestCase,
)
from tests.integration.src.sqlbuild.executor.run.helpers import (
    ExtraAuditDefinition,
    build_reuse_table_plan_entry,
    build_test_audit_gate_metadata,
    build_test_audit_plan_entry,
    create_python_hook_data,
    fail_table_hook,
    insert_table_hook_log,
    run_failure_test,
    run_success_test,
    verify_failure_warehouse_state,
    verify_success_warehouse_state,
    write_matching_reuse_origin_fingerprint,
)


class ZeroCopyDuckDbAdapter(DuckDbAdapter):
    """DuckDB test adapter that exercises the cheap-reuse executor path."""

    adapter_name: ClassVar[str] = "duckdb_zero_copy_test"

    def supports_zero_copy_clone(self) -> bool:
        return True


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
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
    [
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
                ExtraAuditDefinition(
                    name="name_not_null",
                    audit_sql='SELECT name FROM __ref("orders") WHERE name IS NULL',
                    severity="error",
                ),
            ),
            expected_failed_phase=ExecutionPhase.AUDIT,
            expected_staging_relation="staging.orders__staging",
            expected_audit_count=2,
        ),
    ],
    ids=lambda case: case.description,
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
    [
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
    ],
    ids=lambda case: case.description,
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
    [
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
            post_hook=[SqlHookEntry(statement="THIS IS NOT VALID SQL")],
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
    ],
    ids=lambda case: case.description,
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
    [
        TableSuccessTestCase(
            description="pre_hook runs before materialization",
            setup_sql=(),
            model_sql="SELECT * FROM staging.hook_data",
            target_schema="staging",
            target_name="orders",
            promotion_mode=TablePromotionMode.STAGED,
            pre_hook=[SqlHookEntry(statement="CREATE TABLE staging.hook_data AS SELECT 42 AS val")],
            expected_row_count=1,
        ),
        TableSuccessTestCase(
            description="post_hook runs after promotion",
            setup_sql=(),
            model_sql="SELECT 1 AS id",
            target_schema="staging",
            target_name="orders",
            promotion_mode=TablePromotionMode.STAGED,
            post_hook=[
                SqlHookEntry(statement="CREATE TABLE staging.post_hook_ran AS SELECT 1 AS marker")
            ],
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
                SqlHookEntry(statement="CREATE TABLE staging.hook_step_1 AS SELECT 42 AS val"),
                SqlHookEntry(
                    statement="CREATE TABLE staging.hook_step_2 AS SELECT * FROM staging.hook_step_1"
                ),
            ],
            expected_row_count=1,
        ),
        TableSuccessTestCase(
            description="python pre_hook runs before table materialization",
            setup_sql=(),
            model_sql="SELECT * FROM staging.python_hook_data",
            target_schema="staging",
            target_name="orders",
            promotion_mode=TablePromotionMode.STAGED,
            pre_hook=[PythonHookEntry(name="create_data", kwargs={"value": 42})],
            hook_functions=(
                DiscoveredHookFunction(
                    file_path=Path(__file__),
                    relative_path=Path("hooks/table.py"),
                    name="create_data",
                    function=create_python_hook_data,
                ),
            ),
            expected_row_count=1,
            expected_lifecycle_event_fragments=(
                "CREATE TABLE staging.python_hook_data AS SELECT 42 AS val",
                "python pre-hook created data for orders",
            ),
        ),
        TableSuccessTestCase(
            description="mixed SQL and Python hooks execute around table materialization",
            setup_sql=("CREATE TABLE staging.hook_log (phase VARCHAR)",),
            model_sql="SELECT 1 AS id",
            target_schema="staging",
            target_name="orders",
            promotion_mode=TablePromotionMode.STAGED,
            pre_hook=[
                SqlHookEntry(statement="INSERT INTO staging.hook_log VALUES ('sql_pre')"),
                PythonHookEntry(name="insert_hook_log", kwargs={"phase": "python_pre"}),
            ],
            post_hook=[
                PythonHookEntry(name="insert_hook_log", kwargs={"phase": "python_post"}),
                SqlHookEntry(statement="INSERT INTO staging.hook_log VALUES ('sql_post')"),
            ],
            hook_functions=(
                DiscoveredHookFunction(
                    file_path=Path(__file__),
                    relative_path=Path("hooks/table.py"),
                    name="insert_hook_log",
                    function=insert_table_hook_log,
                ),
            ),
            expected_row_count=1,
            expected_query_results=(
                (
                    "SELECT phase FROM staging.hook_log ORDER BY rowid",
                    (("sql_pre",), ("python_pre",), ("python_post",), ("sql_post",)),
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
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
    [
        TableFailureTestCase(
            description="failing pre_hook blocks model",
            setup_sql=(),
            model_sql="SELECT 1 AS id",
            target_schema="staging",
            target_name="orders",
            promotion_mode=TablePromotionMode.STAGED,
            pre_hook=[SqlHookEntry(statement="THIS IS NOT VALID SQL")],
            expected_failed_phase=ExecutionPhase.PRE_HOOK,
        ),
        TableFailureTestCase(
            description="failing post_hook marks model failed after promotion",
            setup_sql=(),
            model_sql="SELECT 1 AS id",
            target_schema="staging",
            target_name="orders",
            promotion_mode=TablePromotionMode.STAGED,
            post_hook=[SqlHookEntry(statement="THIS IS NOT VALID SQL")],
            expected_failed_phase=ExecutionPhase.POST_HOOK,
            expected_promoted_relation="staging.orders",
            expected_row_count=1,
        ),
        TableFailureTestCase(
            description="python post_hook failure marks table failed after promotion",
            setup_sql=(),
            model_sql="SELECT 1 AS id",
            target_schema="staging",
            target_name="orders",
            promotion_mode=TablePromotionMode.STAGED,
            post_hook=[PythonHookEntry(name="fail_hook", kwargs={"message": "table post failed"})],
            hook_functions=(
                DiscoveredHookFunction(
                    file_path=Path(__file__),
                    relative_path=Path("hooks/table.py"),
                    name="fail_hook",
                    function=fail_table_hook,
                ),
            ),
            expected_failed_phase=ExecutionPhase.POST_HOOK,
            expected_error_fragment='post_hooks[0] python("fail_hook") failed: table post failed',
            expected_promoted_relation="staging.orders",
            expected_row_count=1,
        ),
    ],
    ids=lambda case: case.description,
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
    [
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
    ],
    ids=lambda case: case.description,
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
    [
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
    ],
    ids=lambda case: case.description,
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
        TableReuseExecutionTestCase(
            description="staged hard-copy reuse promotes reused relation",
            reuse_hard_copy=True,
            promotion_mode=TablePromotionMode.STAGED,
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((7,),),
            expected_lifecycle_fragments=(
                "DROP TABLE IF EXISTS staging.orders__staging",
                "CREATE OR REPLACE TABLE staging.orders__staging AS SELECT * "
                "FROM staging.orders_origin",
                "RENAME TO orders",
            ),
        ),
        TableReuseExecutionTestCase(
            description="direct hard-copy reuse replaces target with reused relation",
            reuse_hard_copy=True,
            promotion_mode=TablePromotionMode.DIRECT,
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((7,),),
            expected_lifecycle_fragments=(
                "DROP TABLE IF EXISTS staging.orders",
                "CREATE OR REPLACE TABLE staging.orders AS SELECT * FROM staging.orders_origin",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_hard_copy_reuse_relation_when_executing_table_then_materializes_from_origin(
    test_case: TableReuseExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute("CREATE TABLE staging.orders_origin AS SELECT 7 AS id")
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="staging",
        model_name="orders",
        target_name="orders_origin",
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=test_case.reuse_hard_copy,
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(),
            run_id="test_run",
            query_change_tracking=False,
        ),
        declared_columns=(),
        promotion_mode=test_case.promotion_mode,
    )

    rows: list[tuple[Any, ...]] = connection.execute("SELECT * FROM staging.orders").fetchall()
    lifecycle_sql: tuple[str, ...] = tuple(event.content for event in result.lifecycle_events)
    assert result.status == test_case.expected_status
    assert rows == list(test_case.expected_rows)
    for fragment in test_case.expected_lifecycle_fragments:
        assert any(fragment in statement for statement in lifecycle_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        TableReuseExecutionTestCase(
            description="cheap reuse with adapter support materializes from origin",
            reuse_hard_copy=False,
            promotion_mode=TablePromotionMode.STAGED,
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((7,),),
            expected_lifecycle_fragments=(
                "CREATE OR REPLACE TABLE staging.orders__staging AS SELECT * "
                "FROM staging.orders_origin",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cheap_reuse_with_adapter_support_when_executing_table_then_materializes_from_origin(
    test_case: TableReuseExecutionTestCase,
    connection: Any,
) -> None:
    adapter: ZeroCopyDuckDbAdapter = ZeroCopyDuckDbAdapter()
    connection.execute("CREATE TABLE staging.orders_origin AS SELECT 7 AS id")
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="staging",
        model_name="orders",
        target_name="orders_origin",
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=test_case.reuse_hard_copy,
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(),
            run_id="test_run",
            query_change_tracking=False,
        ),
        declared_columns=(),
        promotion_mode=test_case.promotion_mode,
    )

    rows: list[tuple[Any, ...]] = connection.execute("SELECT * FROM staging.orders").fetchall()
    lifecycle_sql: tuple[str, ...] = tuple(event.content for event in result.lifecycle_events)
    assert result.status == test_case.expected_status
    assert rows == list(test_case.expected_rows)
    for fragment in test_case.expected_lifecycle_fragments:
        assert any(fragment in statement for statement in lifecycle_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        TableReuseExecutionTestCase(
            description="cheap reuse without adapter support fails clearly",
            reuse_hard_copy=False,
            promotion_mode=TablePromotionMode.STAGED,
            expected_status=ExecutionStatus.FAILED.value,
            expected_error_fragments=(
                "adapter 'duckdb'",
                "does not support cheap relation reuse",
                "reuse_hard_copy = false",
                "will not copy production relations automatically",
                "reuse_hard_copy = true",
                "remove reuse_from to build normally",
            ),
            expected_target_exists=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cheap_reuse_without_adapter_support_when_executing_table_then_fails_clearly(
    test_case: TableReuseExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute("CREATE TABLE staging.orders_origin AS SELECT 7 AS id")
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="staging",
        model_name="orders",
        target_name="orders_origin",
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=test_case.reuse_hard_copy,
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(),
            run_id="test_run",
            query_change_tracking=False,
        ),
        declared_columns=(),
        promotion_mode=test_case.promotion_mode,
    )

    assert result.status == test_case.expected_status
    assert result.failed_phase == ExecutionPhase.STAGING
    assert result.error_message is not None
    for fragment in test_case.expected_error_fragments:
        assert fragment in result.error_message
    fingerprint_rows: list[tuple[object, ...]] = connection.execute(
        "SELECT node_name, target_name FROM staging._sqlbuild_fingerprints "
        "WHERE node_name = 'orders' ORDER BY target_name"
    ).fetchall()
    assert fingerprint_rows == [("orders", "orders_origin")]
    target_exists: bool = connection.execute(
        "SELECT COUNT(*) FROM duckdb_tables() WHERE schema_name = 'staging' "
        "AND table_name = 'orders'"
    ).fetchone() != (0,)
    assert target_exists is test_case.expected_target_exists


@pytest.mark.parametrize(
    "test_case",
    [
        TableReuseFailureExecutionTestCase(
            description="fingerprint mismatch before table reuse fails before copy",
            setup_sql=("CREATE TABLE staging.orders_origin AS SELECT 7 AS id",),
            fingerprint_version_hash="stale_version",
            expected_status=ExecutionStatus.FAILED.value,
            expected_failed_phase=ExecutionPhase.STAGING,
            expected_error_fragments=(
                "cannot reuse from target 'prod'",
                "reuse origin fingerprint changed after planning",
            ),
            expected_target_exists=False,
        ),
        TableReuseFailureExecutionTestCase(
            description="missing origin relation fails before target exists",
            setup_sql=(),
            fingerprint_version_hash="expected_version",
            expected_status=ExecutionStatus.FAILED.value,
            expected_failed_phase=ExecutionPhase.STAGING,
            expected_error_fragments=("orders_origin",),
            expected_target_exists=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_reuse_origin_when_executing_table_then_fails_before_target_replacement(
    test_case: TableReuseFailureExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="staging",
        model_name="orders",
        target_name="orders_origin",
        version_hash=test_case.fingerprint_version_hash,
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=True,
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(),
            run_id="test_run",
            query_change_tracking=False,
        ),
        declared_columns=(),
        promotion_mode=TablePromotionMode.STAGED,
    )

    target_exists: bool = connection.execute(
        "SELECT COUNT(*) FROM duckdb_tables() WHERE schema_name = 'staging' "
        "AND table_name = 'orders'"
    ).fetchone() != (0,)
    assert result.status == test_case.expected_status
    assert result.failed_phase == test_case.expected_failed_phase
    assert result.error_message is not None
    for fragment in test_case.expected_error_fragments:
        assert fragment in result.error_message
    assert target_exists is test_case.expected_target_exists


@pytest.mark.parametrize(
    "test_case",
    [
        TableReuseExecutionTestCase(
            description="database-qualified reuse origin materializes destination",
            reuse_hard_copy=True,
            promotion_mode=TablePromotionMode.STAGED,
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((7,),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_database_qualified_reuse_origin_when_executing_table_then_materializes_destination(
    test_case: TableReuseExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute("ATTACH ':memory:' AS prod_db")
    connection.execute("ATTACH ':memory:' AS dev_db")
    connection.execute("CREATE SCHEMA prod_db.staging")
    connection.execute("CREATE SCHEMA dev_db.staging")
    connection.execute("CREATE TABLE prod_db.staging.orders_origin AS SELECT 7 AS id")
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        database="prod_db",
        schema="staging",
        model_name="orders",
        target_database="prod_db",
        target_name="orders_origin",
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_database="dev_db",
        target_schema="staging",
        target_name="orders",
        origin_database="prod_db",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=test_case.reuse_hard_copy,
        reuse_origin_fingerprint_database="prod_db",
        reuse_origin_fingerprint_schema="staging",
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(),
            run_id="test_run",
            query_change_tracking=False,
        ),
        declared_columns=(),
        promotion_mode=test_case.promotion_mode,
    )

    rows: list[tuple[Any, ...]] = connection.execute(
        "SELECT * FROM dev_db.staging.orders"
    ).fetchall()
    assert result.status == test_case.expected_status
    assert tuple(rows) == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        TableReuseAuditProofExecutionTestCase(
            description="complete table reuse consumes accepted origin audit proof",
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((None,),),
            expected_audit_count=1,
            expected_reused_count=1,
            expected_metadata_reused=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_complete_reuse_with_origin_audit_proof_when_executing_table_then_reuses_audit_gate(
    test_case: TableReuseAuditProofExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    origin_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="staging.orders_origin",
        severity="error",
    )
    planned_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="staging.orders",
        severity="error",
    )
    connection.execute("CREATE TABLE staging.orders_origin AS SELECT NULL AS id")
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="staging",
        model_name="orders",
        target_name="orders_origin",
        metadata_json=build_test_audit_gate_metadata(audit=origin_audit),
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=True,
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(planned_audit,),
            run_id="test_run",
            query_change_tracking=True,
        ),
        declared_columns=(),
        promotion_mode=TablePromotionMode.STAGED,
    )

    rows: list[tuple[Any, ...]] = connection.execute("SELECT * FROM staging.orders").fetchall()
    destination_metadata_json_b64: str = connection.execute(
        "SELECT metadata_json_b64 FROM staging._sqlbuild_fingerprints "
        "WHERE node_name = 'orders' AND target_name = 'orders' AND run_id = 'test_run'"
    ).fetchone()[0]
    destination_metadata_json: str = base64.b64decode(destination_metadata_json_b64).decode()
    destination_metadata: Any = json.loads(destination_metadata_json)
    destination_results: Any = destination_metadata["audit_gate"]["results"]
    assert result.status == test_case.expected_status
    assert tuple(rows) == test_case.expected_rows
    assert len(result.audit_results) == test_case.expected_audit_count
    assert (
        sum(audit_result.reused for audit_result in result.audit_results)
        == test_case.expected_reused_count
    )
    assert destination_results[0]["reused"] is test_case.expected_metadata_reused


@pytest.mark.parametrize(
    "test_case",
    [
        TableReuseAuditProofExecutionTestCase(
            description="missing origin audit proof executes blocking audit and blocks promotion",
            expected_status=ExecutionStatus.FAILED.value,
            expected_rows=(),
            expected_audit_count=1,
            expected_reused_count=0,
            expected_metadata_reused=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_complete_reuse_without_origin_audit_proof_when_executing_table_then_blocks_bad_data(
    test_case: TableReuseAuditProofExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    planned_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="staging.orders",
        severity="error",
    )
    connection.execute("CREATE TABLE staging.orders_origin AS SELECT NULL AS id")
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="staging",
        model_name="orders",
        target_name="orders_origin",
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=True,
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(planned_audit,),
            run_id="test_run",
            query_change_tracking=True,
        ),
        declared_columns=(),
        promotion_mode=TablePromotionMode.STAGED,
    )

    target_exists: bool = connection.execute(
        "SELECT COUNT(*) FROM duckdb_tables() WHERE schema_name = 'staging' "
        "AND table_name = 'orders'"
    ).fetchone() != (0,)
    assert result.status.value == test_case.expected_status
    assert result.failed_phase == ExecutionPhase.AUDIT
    assert target_exists is False
    assert len(result.audit_results) == test_case.expected_audit_count
    assert (
        sum(audit_result.reused for audit_result in result.audit_results)
        == test_case.expected_reused_count
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TableReuseAuditProofExecutionTestCase(
            description="failed origin audit proof executes blocking audit and blocks promotion",
            expected_status=ExecutionStatus.FAILED.value,
            expected_rows=(),
            expected_audit_count=1,
            expected_reused_count=0,
            expected_metadata_reused=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_complete_reuse_with_failed_origin_proof_when_executing_then_blocks_bad_data(
    test_case: TableReuseAuditProofExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    origin_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="staging.orders_origin",
        severity="error",
    )
    planned_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="staging.orders",
        severity="error",
    )
    connection.execute("CREATE TABLE staging.orders_origin AS SELECT NULL AS id")
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="staging",
        model_name="orders",
        target_name="orders_origin",
        metadata_json=build_test_audit_gate_metadata(
            audit=origin_audit,
            outcome=AuditOutcome.ERROR,
        ),
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=True,
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(planned_audit,),
            run_id="test_run",
            query_change_tracking=True,
        ),
        declared_columns=(),
        promotion_mode=TablePromotionMode.STAGED,
    )

    target_exists: bool = connection.execute(
        "SELECT COUNT(*) FROM duckdb_tables() WHERE schema_name = 'staging' "
        "AND table_name = 'orders'"
    ).fetchone() != (0,)
    assert result.status.value == test_case.expected_status
    assert result.failed_phase == ExecutionPhase.AUDIT
    assert target_exists is False
    assert len(result.audit_results) == test_case.expected_audit_count
    assert (
        sum(audit_result.reused for audit_result in result.audit_results)
        == test_case.expected_reused_count
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TableReuseAuditProofExecutionTestCase(
            description="changed origin audit proof executes blocking audit and blocks promotion",
            expected_status=ExecutionStatus.FAILED.value,
            expected_rows=(),
            expected_audit_count=1,
            expected_reused_count=0,
            expected_metadata_reused=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_complete_reuse_with_changed_origin_proof_when_executing_then_blocks_bad_data(
    test_case: TableReuseAuditProofExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    origin_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id < 0',
        attached_target_name="orders",
        resolved_target_name="staging.orders_origin",
        severity="error",
    )
    planned_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="staging.orders",
        severity="error",
    )
    connection.execute("CREATE TABLE staging.orders_origin AS SELECT NULL AS id")
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="staging",
        model_name="orders",
        target_name="orders_origin",
        metadata_json=build_test_audit_gate_metadata(audit=origin_audit),
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=True,
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(planned_audit,),
            run_id="test_run",
            query_change_tracking=True,
        ),
        declared_columns=(),
        promotion_mode=TablePromotionMode.STAGED,
    )

    target_exists: bool = connection.execute(
        "SELECT COUNT(*) FROM duckdb_tables() WHERE schema_name = 'staging' "
        "AND table_name = 'orders'"
    ).fetchone() != (0,)
    assert result.status.value == test_case.expected_status
    assert result.failed_phase == ExecutionPhase.AUDIT
    assert target_exists is False
    assert len(result.audit_results) == test_case.expected_audit_count
    assert (
        sum(audit_result.reused for audit_result in result.audit_results)
        == test_case.expected_reused_count
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TableReuseAuditProofExecutionTestCase(
            description="warn audit under complete reuse executes rather than using proof",
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((None,),),
            expected_audit_count=1,
            expected_reused_count=0,
            expected_metadata_reused=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_complete_reuse_with_warn_audit_when_executing_table_then_warn_audit_runs(
    test_case: TableReuseAuditProofExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    planned_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_warn",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="staging.orders",
        severity="warn",
    )
    connection.execute("CREATE TABLE staging.orders_origin AS SELECT NULL AS id")
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="staging",
        model_name="orders",
        target_name="orders_origin",
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=True,
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(planned_audit,),
            run_id="test_run",
            query_change_tracking=True,
        ),
        declared_columns=(),
        promotion_mode=TablePromotionMode.STAGED,
    )

    rows: list[tuple[Any, ...]] = connection.execute("SELECT * FROM staging.orders").fetchall()
    assert result.status.value == test_case.expected_status
    assert tuple(rows) == test_case.expected_rows
    assert len(result.audit_results) == test_case.expected_audit_count
    assert result.audit_results[0].outcome == AuditOutcome.WARN
    assert (
        sum(audit_result.reused for audit_result in result.audit_results)
        == test_case.expected_reused_count
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TableReuseAuditProofExecutionTestCase(
            description="direct complete reuse consumes accepted origin audit proof",
            expected_status=ExecutionStatus.SUCCESS.value,
            expected_rows=((None,),),
            expected_audit_count=1,
            expected_reused_count=1,
            expected_metadata_reused=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_complete_reuse_with_origin_proof_when_executing_then_reuses_gate(
    test_case: TableReuseAuditProofExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    origin_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="staging.orders_origin",
        severity="error",
    )
    planned_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="staging.orders",
        severity="error",
    )
    connection.execute("CREATE TABLE staging.orders_origin AS SELECT NULL AS id")
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="staging",
        model_name="orders",
        target_name="orders_origin",
        metadata_json=build_test_audit_gate_metadata(audit=origin_audit),
    )
    entry: ModelPlanEntry = build_reuse_table_plan_entry(
        name="orders",
        sql="SELECT 1 AS id",
        target_schema="staging",
        target_name="orders",
        origin_schema="staging",
        origin_name="orders_origin",
        hard_copy=True,
    )

    result: ModelExecutionResult = execute_table_entry(
        context=ModelMaterializationContext(
            entry=entry,
            adapter=adapter,
            connection=connection,
            model_locations={"orders": entry.destination},
            seed_locations={},
            source_map={},
            model_audits=(planned_audit,),
            run_id="test_run",
            query_change_tracking=True,
        ),
        declared_columns=(),
        promotion_mode=TablePromotionMode.DIRECT,
    )

    rows: list[tuple[Any, ...]] = connection.execute("SELECT * FROM staging.orders").fetchall()
    assert result.status.value == test_case.expected_status
    assert tuple(rows) == test_case.expected_rows
    assert len(result.audit_results) == test_case.expected_audit_count
    assert (
        sum(audit_result.reused for audit_result in result.audit_results)
        == test_case.expected_reused_count
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
    ids=lambda case: case.description,
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
