"""Integration tests for incremental model execution lifecycle."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry, RelationReusePlan
from sqlbuild.compiler.planner.types import OnSchemaChange, RelationReuseKind
from sqlbuild.executor.run.helpers.materializations.incremental import execute_incremental_entry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.shared.models import PythonHookEntry, SqlHookEntry
from tests.integration.src.sqlbuild.executor.run.helpers import (
    build_test_audit_gate_metadata,
    build_test_audit_plan_entry,
    write_matching_reuse_origin_fingerprint,
)
from tests.integration.src.sqlbuild.executor.run.incremental._test_types import (
    IncrementalFailureTestCase,
    IncrementalSeedReuseFailureTestCase,
    IncrementalSeedReuseTestCase,
    IncrementalSuccessTestCase,
)
from tests.integration.src.sqlbuild.executor.run.incremental.helpers import (
    build_incremental_plan_entry,
    fail_incremental_hook,
    insert_incremental_hook_log,
    run_failure_test,
    run_success_test,
    verify_failure_state,
    verify_success_state,
)


class ZeroCopyDuckDbAdapter(DuckDbAdapter):
    """DuckDB test adapter that exercises the cheap-reuse executor path."""

    adapter_name: ClassVar[str] = "duckdb_zero_copy_incremental_test"

    def supports_zero_copy_clone(self) -> bool:
        return True


@pytest.mark.parametrize(
    "test_case",
    [
        IncrementalSuccessTestCase(
            description="model-backed cursor input resolves runtime bounds for normal incremental",
            setup_sql=(
                "CREATE TABLE main.fact_orders ("
                "order_id INTEGER, customer_id INTEGER, order_status VARCHAR, "
                "ordered_at TIMESTAMP, line_total_cents INTEGER)",
                "INSERT INTO main.fact_orders VALUES "
                "(1, 10, 'completed', '2026-01-01 00:30:00', 100), "
                "(2, 11, 'completed', '2026-01-01 01:30:00', 200)",
                "CREATE TABLE main.order_status_index ("
                "order_id INTEGER, customer_id INTEGER, order_status VARCHAR, "
                "ordered_at TIMESTAMP, line_total_cents INTEGER)",
            ),
            model_sql=(
                "SELECT order_id, customer_id, order_status, ordered_at, line_total_cents "
                "FROM main.fact_orders"
            ),
            target_schema="main",
            target_name="order_status_index",
            incremental_strategy="delete_insert",
            cursor_column="order_id",
            cursor_type="integer",
            cursor_input_relations=(("main.fact_orders", "order_id"),),
            cursor_inputs_model_backed=True,
            expected_row_count=2,
            expected_query_results=(
                (
                    "SELECT order_id, customer_id FROM main.order_status_index ORDER BY order_id",
                    ((1, 10), (2, 11)),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="append strategy adds new rows to existing table",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            expected_row_count=2,
            expected_query_results=(
                (
                    "SELECT id, name FROM main.orders ORDER BY id",
                    ((1, "alice"), (2, "bob")),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="delete_insert replaces matching rows by key",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice'), (2, 'bob')",
            ),
            model_sql="SELECT 1 AS id, 'alice_updated' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="delete_insert",
            unique_key=("id",),
            expected_row_count=2,
            expected_query_results=(
                (
                    "SELECT id, name FROM main.orders ORDER BY id",
                    ((1, "alice_updated"), (2, "bob")),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="merge upserts matching rows and inserts new ones",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice'), (2, 'bob')",
            ),
            model_sql="SELECT 1 AS id, 'alice_updated' AS name UNION ALL SELECT 3, 'charlie'",
            target_schema="main",
            target_name="orders",
            incremental_strategy="merge",
            unique_key=("id",),
            expected_row_count=3,
            expected_query_results=(
                (
                    "SELECT id, name FROM main.orders ORDER BY id",
                    ((1, "alice_updated"), (2, "bob"), (3, "charlie")),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="append_new_columns adds column to target and appends rows",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name, 100 AS amount",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
            expected_row_count=2,
            expected_column_names=("id", "name", "amount"),
            expected_query_results=(
                (
                    "SELECT id, name, amount FROM main.orders ORDER BY id",
                    ((1, "alice", None), (2, "bob", 100)),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="append_new_columns with removed column uses intersection",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR, old_col VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice', 'old_value')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
            expected_row_count=2,
            expected_warning_count=0,
            expected_query_results=(
                (
                    "SELECT id, name, old_col FROM main.orders ORDER BY id",
                    ((1, "alice", "old_value"), (2, "bob", None)),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="on_schema_change ignore does not alter target and warns",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name, 100 AS amount",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            on_schema_change=OnSchemaChange.IGNORE,
            expected_row_count=2,
            expected_warning_count=1,
            expected_column_names=("id", "name"),
            expected_query_results=(
                (
                    "SELECT id, name FROM main.orders ORDER BY id",
                    ((1, "alice"), (2, "bob")),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="sync_all_columns adds new and drops removed columns",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR, old_col VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice', 'old_value')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name, 200 AS amount",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            on_schema_change=OnSchemaChange.SYNC_ALL_COLUMNS,
            expected_row_count=2,
            expected_column_names=("id", "name", "amount"),
            expected_query_results=(
                (
                    "SELECT id, name, amount FROM main.orders ORDER BY id",
                    ((1, "alice", None), (2, "bob", 200)),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="delta_and_final audit runs in both phases",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            audit_sql='SELECT id FROM __ref("orders") WHERE id < 0',
            audit_severity="warn",
            audit_run_scope=AuditRunScope.DELTA_AND_FINAL,
            expected_row_count=2,
            expected_audit_count=2,
        ),
        IncrementalSuccessTestCase(
            description="final only audit runs once after DML",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            audit_sql='SELECT id FROM __ref("orders") WHERE id < 0',
            audit_severity="warn",
            audit_run_scope=AuditRunScope.FINAL,
            expected_row_count=2,
            expected_audit_count=1,
        ),
        IncrementalSuccessTestCase(
            description="pre and post hooks execute around incremental lifecycle",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
                "CREATE TABLE main.hook_log (phase VARCHAR)",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            pre_hook=[SqlHookEntry(statement="INSERT INTO main.hook_log VALUES ('pre')")],
            post_hook=[SqlHookEntry(statement="INSERT INTO main.hook_log VALUES ('post')")],
            expected_row_count=2,
            expected_query_results=(
                (
                    "SELECT phase FROM main.hook_log ORDER BY phase",
                    (("post",), ("pre",)),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="python pre and post hooks execute around incremental lifecycle",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
                "CREATE TABLE main.hook_log (phase VARCHAR)",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            pre_hook=[PythonHookEntry(name="insert_hook_log", kwargs={"phase": "pre"})],
            post_hook=[PythonHookEntry(name="insert_hook_log", kwargs={"phase": "post"})],
            hook_functions=(
                DiscoveredHookFunction(
                    file_path=Path(__file__),
                    relative_path=Path("hooks/incremental.py"),
                    name="insert_hook_log",
                    function=insert_incremental_hook_log,
                ),
            ),
            expected_row_count=2,
            expected_query_results=(
                (
                    "SELECT phase FROM main.hook_log ORDER BY phase",
                    (("post",), ("pre",)),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="merge with removed column preserves target-only values quietly",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR, old_col VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice', 'preserved'), (2, 'bob', 'also_kept')",
            ),
            model_sql="SELECT 1 AS id, 'alice_updated' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="merge",
            unique_key=("id",),
            on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
            expected_row_count=2,
            expected_warning_count=0,
            expected_query_results=(
                (
                    "SELECT id, name, old_col FROM main.orders ORDER BY id",
                    ((1, "alice_updated", "preserved"), (2, "bob", "also_kept")),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="delete_insert with composite key replaces correctly",
            setup_sql=(
                "CREATE TABLE main.orders (region VARCHAR, id INTEGER, amount INTEGER)",
                "INSERT INTO main.orders VALUES ('us', 1, 100), ('eu', 1, 200), ('us', 2, 300)",
            ),
            model_sql="SELECT 'us' AS region, 1 AS id, 999 AS amount",
            target_schema="main",
            target_name="orders",
            incremental_strategy="delete_insert",
            unique_key=("region", "id"),
            expected_row_count=3,
            expected_query_results=(
                (
                    "SELECT region, id, amount FROM main.orders ORDER BY region, id",
                    (("eu", 1, 200), ("us", 1, 999), ("us", 2, 300)),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="sync_all_columns alters column type when adapter supports it",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, val VARCHAR)",
                "INSERT INTO main.orders VALUES (1, '100')",
            ),
            model_sql="SELECT 2 AS id, 200 AS val",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            on_schema_change=OnSchemaChange.SYNC_ALL_COLUMNS,
            expected_row_count=2,
            expected_query_results=(
                (
                    "SELECT id, val FROM main.orders ORDER BY id",
                    ((1, 100), (2, 200)),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="merge with ignore preserves target schema and uses intersection columns",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR, old_col VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice', 'kept'), (2, 'bob', 'also_kept')",
            ),
            model_sql="SELECT 1 AS id, 'alice_updated' AS name, 999 AS new_col",
            target_schema="main",
            target_name="orders",
            incremental_strategy="merge",
            unique_key=("id",),
            on_schema_change=OnSchemaChange.IGNORE,
            expected_row_count=2,
            expected_warning_count=2,
            expected_column_names=("id", "name", "old_col"),
            expected_query_results=(
                (
                    "SELECT id, name, old_col FROM main.orders ORDER BY id",
                    ((1, "alice_updated", "kept"), (2, "bob", "also_kept")),
                ),
            ),
        ),
        IncrementalSuccessTestCase(
            description="missing target schema warns on incremental when query tracking is enabled",
            setup_sql=(
                "CREATE TABLE orders (id INTEGER, name VARCHAR)",
                "INSERT INTO orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema=None,
            target_name="orders",
            incremental_strategy="append",
            expected_row_count=2,
            expected_warning_count=1,
        ),
        IncrementalSuccessTestCase(
            description="cursor delete_insert uses cursor range over unique_key",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
                "INSERT INTO main.orders VALUES "
                "(1, '2026-01-01 00:30:00', 'a'), "
                "(2, '2026-01-01 00:45:00', 'b'), "
                "(3, '2026-01-01 01:30:00', 'c')",
            ),
            model_sql=(
                "SELECT 1 AS id, '2026-01-01 00:30:00'::TIMESTAMP AS event_time, 'new_a' AS payload"
            ),
            target_schema="main",
            target_name="orders",
            incremental_strategy="delete_insert",
            unique_key=("id",),
            cursor_column="event_time",
            cursor_start="2026-01-01T00:00:00",
            cursor_end="2026-01-01T01:00:00",
            expected_row_count=2,
            expected_query_results=(
                (
                    "SELECT id, payload FROM main.orders ORDER BY id",
                    ((1, "new_a"), (3, "c")),
                ),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_table_when_running_incremental_then_succeeds(
    test_case: IncrementalSuccessTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_success_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.status == test_case.expected_status
    verify_success_state(result=result, test_case=test_case, connection=connection)


@pytest.mark.parametrize(
    "test_case",
    [
        IncrementalFailureTestCase(
            description="sync_all_columns fails on incompatible type change",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, val VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'not_a_number')",
            ),
            model_sql="SELECT 2 AS id, 200 AS val",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            on_schema_change=OnSchemaChange.SYNC_ALL_COLUMNS,
            expected_failed_phase=ExecutionPhase.SCHEMA_CHANGE,
            expected_error_fragment="Conversion Error",
            expected_staging_relation="main.orders__delta",
            expected_row_count=1,
        ),
        IncrementalFailureTestCase(
            description="on_schema_change fail rejects schema diff before DML",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name, 100 AS amount",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            on_schema_change=OnSchemaChange.FAIL,
            expected_failed_phase=ExecutionPhase.SCHEMA_CHANGE,
            expected_error_fragment="on_schema_change is set to fail",
            expected_staging_relation="main.orders__delta",
            expected_row_count=1,
        ),
        IncrementalFailureTestCase(
            description="append_new_columns rejects type change",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 999 AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
            expected_failed_phase=ExecutionPhase.SCHEMA_CHANGE,
            expected_error_fragment="does not support type changes",
            expected_staging_relation="main.orders__delta",
            expected_row_count=1,
        ),
        IncrementalFailureTestCase(
            description="delta audit error blocks DML via override to delta relation",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            audit_sql='SELECT id FROM __ref("orders") WHERE id = 2',
            audit_severity="error",
            audit_run_scope=AuditRunScope.DELTA_AND_FINAL,
            expected_failed_phase=ExecutionPhase.AUDIT,
            expected_error_fragment="delta audit for 'orders' failed before target update",
            expected_staging_relation="main.orders__delta",
            expected_audit_count=1,
            expected_row_count=1,
        ),
        IncrementalFailureTestCase(
            description="final audit error after DML reports target already updated",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            audit_sql='SELECT id FROM __ref("orders") WHERE id > 0',
            audit_severity="error",
            audit_run_scope=AuditRunScope.FINAL,
            expected_failed_phase=ExecutionPhase.AUDIT,
            expected_error_fragment="final audit for 'orders' failed after target update",
            expected_staging_relation="main.orders__delta",
            expected_promoted_relation="main.orders",
            expected_audit_count=1,
            expected_row_count=2,
        ),
        IncrementalFailureTestCase(
            description="pre_hook failure blocks incremental execution",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            pre_hook=[SqlHookEntry(statement="SELECT * FROM nonexistent_table_for_hook")],
            expected_failed_phase=ExecutionPhase.PRE_HOOK,
            expected_row_count=1,
        ),
        IncrementalFailureTestCase(
            description="python pre_hook failure blocks incremental execution",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            pre_hook=[PythonHookEntry(name="fail_hook", kwargs={"message": "pre boom"})],
            hook_functions=(
                DiscoveredHookFunction(
                    file_path=Path(__file__),
                    relative_path=Path("hooks/incremental.py"),
                    name="fail_hook",
                    function=fail_incremental_hook,
                ),
            ),
            expected_failed_phase=ExecutionPhase.PRE_HOOK,
            expected_error_fragment='pre_hooks[0] python("fail_hook") failed: pre boom',
            expected_row_count=1,
        ),
        IncrementalFailureTestCase(
            description="post_hook failure after DML marks model failed",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            post_hook=[SqlHookEntry(statement="SELECT * FROM nonexistent_table_for_hook")],
            expected_failed_phase=ExecutionPhase.POST_HOOK,
            expected_staging_relation="main.orders__delta",
            expected_promoted_relation="main.orders",
            expected_row_count=2,
        ),
        IncrementalFailureTestCase(
            description="python post_hook failure after DML marks model failed",
            setup_sql=(
                "CREATE TABLE main.orders (id INTEGER, name VARCHAR)",
                "INSERT INTO main.orders VALUES (1, 'alice')",
            ),
            model_sql="SELECT 2 AS id, 'bob' AS name",
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            post_hook=[PythonHookEntry(name="fail_hook", kwargs={"message": "post boom"})],
            hook_functions=(
                DiscoveredHookFunction(
                    file_path=Path(__file__),
                    relative_path=Path("hooks/incremental.py"),
                    name="fail_hook",
                    function=fail_incremental_hook,
                ),
            ),
            expected_failed_phase=ExecutionPhase.POST_HOOK,
            expected_error_fragment='post_hooks[0] python("fail_hook") failed: post boom',
            expected_staging_relation="main.orders__delta",
            expected_promoted_relation="main.orders",
            expected_row_count=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_existing_table_when_incremental_fails_then_reports_correct_phase(
    test_case: IncrementalFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    result: ModelExecutionResult = run_failure_test(
        test_case=test_case, adapter=adapter, connection=connection
    )
    assert result.failed_phase == test_case.expected_failed_phase
    verify_failure_state(result=result, test_case=test_case, connection=connection)


@pytest.mark.parametrize(
    "test_case",
    [
        IncrementalSeedReuseTestCase(
            description="recomputes cursor bounds after seeding from reuse origin",
            origin_sql=(
                "CREATE TABLE main.orders_origin AS "
                "SELECT 1 AS order_id, TIMESTAMP '2026-01-01 00:00:00' AS ordered_at "
                "UNION ALL SELECT 2 AS order_id, TIMESTAMP '2026-01-02 00:00:00' AS ordered_at"
            ),
            input_sql=(
                "CREATE TABLE main.raw_orders AS "
                "SELECT 1 AS order_id, TIMESTAMP '2026-01-01 00:00:00' AS ordered_at "
                "UNION ALL SELECT 2 AS order_id, TIMESTAMP '2026-01-02 00:00:00' AS ordered_at "
                "UNION ALL SELECT 3 AS order_id, TIMESTAMP '2026-01-03 00:00:00' AS ordered_at"
            ),
            model_sql=(
                "SELECT * FROM main.raw_orders WHERE ordered_at > "
                "TIMESTAMP '__SQB_CURSOR_START__' AND ordered_at <= "
                "TIMESTAMP '__SQB_CURSOR_END__'"
            ),
            expected_rows=((1,), (2,), (3,)),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_seeded_incremental_when_running_then_recomputes_cursor_bounds_after_seed(
    test_case: IncrementalSeedReuseTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute(test_case.origin_sql)
    connection.execute(test_case.input_sql)
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="main",
        model_name="orders",
        target_name="orders_origin",
    )
    entry: ModelPlanEntry = dataclasses.replace(
        build_incremental_plan_entry(
            name="orders",
            sql=test_case.model_sql,
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            cursor_column="ordered_at",
            cursor_type="timestamp",
            cursor_input_relations=(("main.raw_orders", "ordered_at"),),
            cursor_inputs_model_backed=True,
        ),
        fingerprint_version_hash="expected_version",
        relation_reuse=RelationReusePlan(
            kind=RelationReuseKind.SEEDED_RELATION_REUSE,
            origin=CompiledRelationLocation(
                database=None,
                schema="main",
                name="orders_origin",
                qualified_name="main.orders_origin",
            ),
            reuse_from_target_name="prod",
            hard_copy=test_case.reuse_hard_copy,
            fingerprint_database=None,
            fingerprint_schema="main",
        ),
    )

    result: ModelExecutionResult = execute_incremental_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_locations={"orders": entry.destination},
        seed_locations={},
        source_map={},
        model_audits=(),
        declared_columns=(),
        run_id="test_run",
        query_change_tracking=False,
    )

    rows: list[tuple[object, ...]] = connection.execute(
        "SELECT order_id FROM main.orders ORDER BY order_id"
    ).fetchall()
    lifecycle_sql: tuple[str, ...] = tuple(event.content for event in result.lifecycle_events)
    assert result.status.value == "success"
    assert tuple(rows) == test_case.expected_rows
    for fragment in test_case.expected_lifecycle_fragments:
        assert any(fragment in statement for statement in lifecycle_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        IncrementalSeedReuseTestCase(
            description="cheap seed reuse with adapter support continues incremental execution",
            origin_sql=(
                "CREATE TABLE main.orders_origin AS "
                "SELECT 1 AS order_id, TIMESTAMP '2026-01-01 00:00:00' AS ordered_at"
            ),
            input_sql=(
                "CREATE TABLE main.raw_orders AS "
                "SELECT 1 AS order_id, TIMESTAMP '2026-01-01 00:00:00' AS ordered_at "
                "UNION ALL SELECT 2 AS order_id, TIMESTAMP '2026-01-02 00:00:00' AS ordered_at"
            ),
            model_sql=(
                "SELECT * FROM main.raw_orders WHERE ordered_at > "
                "TIMESTAMP '__SQB_CURSOR_START__' AND ordered_at <= "
                "TIMESTAMP '__SQB_CURSOR_END__'"
            ),
            expected_rows=((1,), (2,)),
            reuse_hard_copy=False,
            expected_lifecycle_fragments=(
                "CREATE OR REPLACE TABLE main.orders__reuse_seed AS SELECT * "
                "FROM main.orders_origin",
                "ALTER TABLE main.orders__reuse_seed RENAME TO orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cheap_seed_reuse_when_running_incremental_then_materializes_from_origin(
    test_case: IncrementalSeedReuseTestCase,
    connection: Any,
) -> None:
    adapter: ZeroCopyDuckDbAdapter = ZeroCopyDuckDbAdapter()
    connection.execute(test_case.origin_sql)
    connection.execute(test_case.input_sql)
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="main",
        model_name="orders",
        target_name="orders_origin",
    )
    entry: ModelPlanEntry = dataclasses.replace(
        build_incremental_plan_entry(
            name="orders",
            sql=test_case.model_sql,
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            cursor_column="ordered_at",
            cursor_type="timestamp",
            cursor_input_relations=(("main.raw_orders", "ordered_at"),),
            cursor_inputs_model_backed=True,
        ),
        fingerprint_version_hash="expected_version",
        relation_reuse=RelationReusePlan(
            kind=RelationReuseKind.SEEDED_RELATION_REUSE,
            origin=CompiledRelationLocation(
                database=None,
                schema="main",
                name="orders_origin",
                qualified_name="main.orders_origin",
            ),
            reuse_from_target_name="prod",
            hard_copy=test_case.reuse_hard_copy,
            fingerprint_database=None,
            fingerprint_schema="main",
        ),
    )

    result: ModelExecutionResult = execute_incremental_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_locations={"orders": entry.destination},
        seed_locations={},
        source_map={},
        model_audits=(),
        declared_columns=(),
        run_id="test_run",
        query_change_tracking=False,
    )

    rows: list[tuple[object, ...]] = connection.execute(
        "SELECT order_id FROM main.orders ORDER BY order_id"
    ).fetchall()
    lifecycle_sql: tuple[str, ...] = tuple(event.content for event in result.lifecycle_events)
    assert result.status.value == "success"
    assert tuple(rows) == test_case.expected_rows
    for fragment in test_case.expected_lifecycle_fragments:
        assert any(fragment in statement for statement in lifecycle_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        IncrementalSeedReuseFailureTestCase(
            description="incremental seed reuse executes audits despite accepted origin proof",
            origin_sql=(
                "CREATE TABLE main.orders_origin AS "
                "SELECT NULL::INTEGER AS order_id, TIMESTAMP '2026-01-01 00:00:00' AS ordered_at"
            ),
            input_sql=(
                "CREATE TABLE main.raw_orders AS "
                "SELECT 1 AS order_id, TIMESTAMP '2026-01-02 00:00:00' AS ordered_at WHERE 1 = 0"
            ),
            model_sql="SELECT order_id, ordered_at FROM main.raw_orders",
            fingerprint_version_hash="expected_version",
            expected_status=ExecutionStatus.FAILED,
            expected_failed_phase=ExecutionPhase.AUDIT,
            expected_error_fragments=("final audit for 'orders' failed",),
            expected_target_exists=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_incremental_reuse_with_origin_proof_when_running_then_audit_executes(
    test_case: IncrementalSeedReuseFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    origin_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
        attached_target_name="orders",
        resolved_target_name="main.orders_origin",
        severity="error",
    )
    planned_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
        attached_target_name="orders",
        resolved_target_name="main.orders",
        severity="error",
    )
    connection.execute(test_case.origin_sql)
    connection.execute(test_case.input_sql)
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="main",
        model_name="orders",
        target_name="orders_origin",
        metadata_json=build_test_audit_gate_metadata(audit=origin_audit),
    )
    entry: ModelPlanEntry = dataclasses.replace(
        build_incremental_plan_entry(
            name="orders",
            sql=test_case.model_sql,
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
        ),
        fingerprint_version_hash="expected_version",
        relation_reuse=RelationReusePlan(
            kind=RelationReuseKind.SEEDED_RELATION_REUSE,
            origin=CompiledRelationLocation(
                database=None,
                schema="main",
                name="orders_origin",
                qualified_name="main.orders_origin",
            ),
            reuse_from_target_name="prod",
            hard_copy=True,
            fingerprint_database=None,
            fingerprint_schema="main",
        ),
    )

    result: ModelExecutionResult = execute_incremental_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_locations={"orders": entry.destination},
        seed_locations={},
        source_map={},
        model_audits=(planned_audit,),
        declared_columns=(),
        run_id="test_run",
        query_change_tracking=False,
    )

    target_exists: bool = connection.execute(
        "SELECT COUNT(*) FROM duckdb_tables() WHERE schema_name = 'main' AND table_name = 'orders'"
    ).fetchone() != (0,)
    assert result.status == test_case.expected_status
    assert result.failed_phase == test_case.expected_failed_phase
    assert result.error_message is not None
    for fragment in test_case.expected_error_fragments:
        assert fragment in result.error_message
    assert target_exists is test_case.expected_target_exists
    assert len(result.audit_results) == 1
    assert result.audit_results[0].reused is False


@pytest.mark.parametrize(
    "test_case",
    [
        IncrementalSeedReuseFailureTestCase(
            description="fingerprint mismatch before incremental seed fails before target exists",
            origin_sql=(
                "CREATE TABLE main.orders_origin AS "
                "SELECT 1 AS order_id, TIMESTAMP '2026-01-01 00:00:00' AS ordered_at"
            ),
            input_sql=(
                "CREATE TABLE main.raw_orders AS "
                "SELECT 1 AS order_id, TIMESTAMP '2026-01-01 00:00:00' AS ordered_at"
            ),
            model_sql="SELECT * FROM main.raw_orders",
            fingerprint_version_hash="stale_version",
            expected_status=ExecutionStatus.FAILED,
            expected_failed_phase=ExecutionPhase.STAGING,
            expected_error_fragments=(
                "cannot reuse from target 'prod'",
                "reuse origin fingerprint changed after planning",
            ),
            expected_target_exists=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_stale_reuse_origin_fingerprint_when_running_incremental_then_seed_fails(
    test_case: IncrementalSeedReuseFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute(test_case.origin_sql)
    connection.execute(test_case.input_sql)
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="main",
        model_name="orders",
        target_name="orders_origin",
        version_hash=test_case.fingerprint_version_hash,
    )
    entry: ModelPlanEntry = dataclasses.replace(
        build_incremental_plan_entry(
            name="orders",
            sql=test_case.model_sql,
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
        ),
        fingerprint_version_hash="expected_version",
        relation_reuse=RelationReusePlan(
            kind=RelationReuseKind.SEEDED_RELATION_REUSE,
            origin=CompiledRelationLocation(
                database=None,
                schema="main",
                name="orders_origin",
                qualified_name="main.orders_origin",
            ),
            reuse_from_target_name="prod",
            hard_copy=True,
            fingerprint_database=None,
            fingerprint_schema="main",
        ),
    )

    result: ModelExecutionResult = execute_incremental_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_locations={"orders": entry.destination},
        seed_locations={},
        source_map={},
        model_audits=(),
        declared_columns=(),
        run_id="test_run",
        query_change_tracking=False,
    )

    target_exists: bool = connection.execute(
        "SELECT COUNT(*) FROM duckdb_tables() WHERE schema_name = 'main' AND table_name = 'orders'"
    ).fetchone() != (0,)
    assert result.status == test_case.expected_status
    assert result.failed_phase == test_case.expected_failed_phase
    assert result.error_message is not None
    for fragment in test_case.expected_error_fragments:
        assert fragment in result.error_message
    assert target_exists is test_case.expected_target_exists
