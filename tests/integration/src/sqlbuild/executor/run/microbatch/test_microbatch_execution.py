"""Integration tests for microbatch incremental execution lifecycle."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.auditing.types import AuditRunScope
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry, RelationReusePlan
from sqlbuild.compiler.planner.types import OnSchemaChange, RelationReuseKind
from sqlbuild.executor.run.helpers.microbatch import execute_microbatch_entry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.shared.models import PythonHookEntry, SqlHookEntry
from tests.integration.src.sqlbuild.executor.run.helpers import (
    build_test_audit_gate_metadata,
    build_test_audit_plan_entry,
    write_matching_reuse_origin_fingerprint,
)
from tests.integration.src.sqlbuild.executor.run.microbatch._test_types import (
    MicrobatchFailureTestCase,
    MicrobatchSuccessTestCase,
)
from tests.integration.src.sqlbuild.executor.run.microbatch.helpers import (
    build_microbatch_plan_entry,
    fail_microbatch_hook,
    insert_microbatch_hook_log,
    run_failure_test,
    run_success_test,
    verify_failure_state,
    verify_success_state,
)

_TS_SOURCE_SQL: str = (
    "CREATE TABLE main.raw_events (  id INTEGER, event_time TIMESTAMP, payload VARCHAR)"
)
_TS_SOURCE_DATA: str = (
    "INSERT INTO main.raw_events VALUES "
    "(1, '2026-01-01 00:30:00', 'a'), "
    "(2, '2026-01-01 01:30:00', 'b'), "
    "(3, '2026-01-01 02:30:00', 'c')"
)

_TS_MODEL_SQL: str = (
    "SELECT id, event_time, payload FROM main.raw_events "
    f"WHERE event_time >= '{MICROBATCH_START_SENTINEL}' "
    f"AND event_time < '{MICROBATCH_END_SENTINEL}'"
)

_INT_SOURCE_SQL: str = (
    "CREATE TABLE main.raw_events (  id INTEGER, batch_id INTEGER, payload VARCHAR)"
)
_INT_SOURCE_DATA: str = (
    "INSERT INTO main.raw_events VALUES (1, 10, 'a'), (2, 30, 'b'), (3, 70, 'c'), (4, 90, 'd')"
)

_INT_MODEL_SQL: str = (
    "SELECT id, batch_id, payload FROM main.raw_events "
    f"WHERE batch_id >= {MICROBATCH_START_SENTINEL} "
    f"AND batch_id < {MICROBATCH_END_SENTINEL}"
)


SUCCESS_TEST_CASES: list[MicrobatchSuccessTestCase] = [
    MicrobatchSuccessTestCase(
        description="model-backed cursor input resolves runtime range for microbatch",
        setup_sql=(
            "CREATE TABLE main.fact_orders (id INTEGER, ordered_at TIMESTAMP, payload VARCHAR)",
            "INSERT INTO main.fact_orders VALUES "
            "(1, '2026-01-01 00:30:00', 'a'), "
            "(2, '2026-01-01 01:30:00', 'b')",
            "CREATE TABLE main.orders (id INTEGER, activity_hour TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=(
            "SELECT id, DATE_TRUNC('hour', ordered_at) AS activity_hour, payload "
            "FROM main.fact_orders "
            f"WHERE ordered_at >= '{MICROBATCH_START_SENTINEL}' "
            f"AND ordered_at < '{MICROBATCH_END_SENTINEL}'"
        ),
        target_schema="main",
        target_name="orders",
        incremental_strategy="delete_insert",
        cursor_column="activity_hour",
        cursor_type="timestamp",
        cursor_grain="hour",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T02:00:00",
        use_plan_microbatch_range=False,
        cursor_input_relations=(("main.fact_orders", "ordered_at"),),
        cursor_inputs_model_backed=True,
        unique_key=("id",),
        expected_row_count=2,
        expected_query_results=(
            (
                "SELECT id, payload FROM main.orders ORDER BY id",
                ((1, "a"), (2, "b")),
            ),
        ),
    ),
    MicrobatchSuccessTestCase(
        description="timestamp microbatch appends 3 hourly batches",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        expected_row_count=3,
        expected_query_results=(
            (
                "SELECT id, payload FROM main.orders ORDER BY id",
                ((1, "a"), (2, "b"), (3, "c")),
            ),
        ),
        expected_executed_statement_fragments=(
            "CREATE OR REPLACE TABLE main.orders__delta AS SELECT id, event_time, payload",
            "event_time >= '2026-01-01T00:00:00'",
            "event_time < '2026-01-01T01:00:00'",
            "INSERT INTO main.orders SELECT * FROM main.orders__delta",
            "DROP TABLE IF EXISTS main.orders__delta",
        ),
    ),
    MicrobatchSuccessTestCase(
        description="integer microbatch appends 2 batches of size 50",
        setup_sql=(
            _INT_SOURCE_SQL,
            _INT_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, batch_id INTEGER, payload VARCHAR)",
        ),
        model_sql=_INT_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="batch_id",
        cursor_type="integer",
        batch_size="50",
        microbatch_start="0",
        microbatch_end="100",
        expected_row_count=4,
        expected_query_results=(
            (
                "SELECT id, payload FROM main.orders ORDER BY id",
                ((1, "a"), (2, "b"), (3, "c"), (4, "d")),
            ),
        ),
    ),
    MicrobatchSuccessTestCase(
        description="full-refresh microbatch drops target and rebuilds in batches",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
            "INSERT INTO main.orders VALUES (99, '2025-01-01 00:00:00', 'old')",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        is_full_refresh=True,
        cursor_input_relations=(("main.raw_events", "event_time"),),
        expected_row_count=3,
        expected_query_results=(
            (
                "SELECT id, payload FROM main.orders ORDER BY id",
                ((1, "a"), (2, "b"), (3, "c")),
            ),
        ),
    ),
    MicrobatchSuccessTestCase(
        description="full-refresh discovers range from input when output groups away cursor",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
        ),
        model_sql=(
            "SELECT DATE_TRUNC('hour', event_time) AS event_hour, COUNT(*) AS event_count "
            "FROM main.raw_events "
            f"WHERE event_time >= '{MICROBATCH_START_SENTINEL}' "
            f"AND event_time < '{MICROBATCH_END_SENTINEL}' "
            "GROUP BY DATE_TRUNC('hour', event_time)"
        ),
        target_schema="main",
        target_name="order_activity",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        is_full_refresh=True,
        cursor_input_relations=(("main.raw_events", "event_time"),),
        expected_row_count=3,
        expected_query_results=(
            (
                "SELECT CAST(event_hour AS VARCHAR), event_count "
                "FROM main.order_activity ORDER BY event_hour",
                (
                    ("2026-01-01 00:00:00", 1),
                    ("2026-01-01 01:00:00", 1),
                    ("2026-01-01 02:00:00", 1),
                ),
            ),
        ),
    ),
    MicrobatchSuccessTestCase(
        description="delta_and_final audit runs per batch plus once final",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        audit_sql='SELECT id FROM __ref("orders") WHERE id < 0',
        audit_severity="warn",
        audit_run_scope=AuditRunScope.DELTA_AND_FINAL,
        expected_row_count=3,
        expected_audit_count=4,
    ),
    MicrobatchSuccessTestCase(
        description="SQL and Python hooks run once around entire batch loop",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
            "CREATE TABLE main.hook_log (phase VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        pre_hook=[
            SqlHookEntry(statement="INSERT INTO main.hook_log VALUES ('sql_pre')"),
            PythonHookEntry(name="insert_hook_log", kwargs={"phase": "python_pre"}),
        ],
        post_hook=[
            PythonHookEntry(name="insert_hook_log", kwargs={"phase": "python_post"}),
            SqlHookEntry(statement="INSERT INTO main.hook_log VALUES ('sql_post')"),
        ],
        hook_functions=(
            DiscoveredHookFunction(
                file_path=Path(__file__),
                relative_path=Path("hooks/microbatch.py"),
                name="insert_hook_log",
                function=insert_microbatch_hook_log,
            ),
        ),
        expected_row_count=3,
        expected_query_results=(
            (
                "SELECT phase FROM main.hook_log ORDER BY rowid",
                (("sql_pre",), ("python_pre",), ("python_post",), ("sql_post",)),
            ),
        ),
    ),
    MicrobatchSuccessTestCase(
        description="delete_insert microbatch replaces matching rows per batch",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
            "INSERT INTO main.orders VALUES (1, '2026-01-01 00:30:00', 'old_a'), "
            "(2, '2026-01-01 01:30:00', 'old_b')",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="delete_insert",
        unique_key=("id",),
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        expected_row_count=3,
        expected_query_results=(
            (
                "SELECT id, payload FROM main.orders ORDER BY id",
                ((1, "a"), (2, "b"), (3, "c")),
            ),
        ),
    ),
    MicrobatchSuccessTestCase(
        description="cursor-based delete_insert uses cursor range not unique key",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
            "INSERT INTO main.orders VALUES "
            "(1, '2026-01-01 00:30:00', 'old_a'), "
            "(10, '2026-01-01 00:45:00', 'stays'), "
            "(2, '2026-01-01 01:30:00', 'old_b')",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="delete_insert",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        expected_row_count=3,
        expected_query_results=(
            (
                "SELECT id, payload FROM main.orders ORDER BY id",
                ((1, "a"), (2, "b"), (3, "c")),
            ),
        ),
    ),
    MicrobatchSuccessTestCase(
        description="append_new_columns schema change applied on first batch",
        setup_sql=(
            "CREATE TABLE main.raw_events ("
            "  id INTEGER, event_time TIMESTAMP, payload VARCHAR, extra INTEGER"
            ")",
            "INSERT INTO main.raw_events VALUES "
            "(1, '2026-01-01 00:30:00', 'a', 10), "
            "(2, '2026-01-01 01:30:00', 'b', 20)",
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=(
            "SELECT id, event_time, payload, extra FROM main.raw_events "
            f"WHERE event_time >= '{MICROBATCH_START_SENTINEL}' "
            f"AND event_time < '{MICROBATCH_END_SENTINEL}'"
        ),
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        on_schema_change=OnSchemaChange.APPEND_NEW_COLUMNS,
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T02:00:00",
        expected_row_count=2,
        expected_column_names=("id", "event_time", "payload", "extra"),
        expected_query_results=(
            (
                "SELECT id, extra FROM main.orders ORDER BY id",
                ((1, 10), (2, 20)),
            ),
        ),
    ),
    MicrobatchSuccessTestCase(
        description="empty range produces zero batches and succeeds with warning",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T00:00:00",
        expected_row_count=0,
        expected_warning_count=1,
        expected_delta_cleaned=False,
    ),
    MicrobatchSuccessTestCase(
        description="merge microbatch upserts across batches",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
            "INSERT INTO main.orders VALUES (1, '2026-01-01 00:30:00', 'old_a')",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="merge",
        unique_key=("id",),
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        expected_row_count=3,
        expected_query_results=(
            (
                "SELECT id, payload FROM main.orders ORDER BY id",
                ((1, "a"), (2, "b"), (3, "c")),
            ),
        ),
    ),
]

FAILURE_TEST_CASES: list[MicrobatchFailureTestCase] = [
    MicrobatchFailureTestCase(
        description="pre_hook failure blocks all batches",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        pre_hook=[SqlHookEntry(statement="SELECT * FROM nonexistent_table_for_hook")],
        expected_failed_phase=ExecutionPhase.PRE_HOOK,
        expected_row_count=0,
    ),
    MicrobatchFailureTestCase(
        description="python pre_hook failure blocks all batches",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        pre_hook=[PythonHookEntry(name="fail_hook", kwargs={"message": "microbatch pre failed"})],
        hook_functions=(
            DiscoveredHookFunction(
                file_path=Path(__file__),
                relative_path=Path("hooks/microbatch.py"),
                name="fail_hook",
                function=fail_microbatch_hook,
            ),
        ),
        expected_failed_phase=ExecutionPhase.PRE_HOOK,
        expected_error_fragment='pre_hooks[0] python("fail_hook") failed: microbatch pre failed',
        expected_row_count=0,
    ),
    MicrobatchFailureTestCase(
        description="delta audit error on batch stops remaining batches",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        audit_sql='SELECT id FROM __ref("orders") WHERE id > 0',
        audit_severity="error",
        audit_run_scope=AuditRunScope.DELTA_AND_FINAL,
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_error_fragment="batch 0",
        expected_audit_count=1,
        expected_row_count=0,
    ),
    MicrobatchFailureTestCase(
        description="delta audit failure on later batch preserves earlier completed batches",
        setup_sql=(
            "CREATE TABLE main.raw_events (  id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
            "INSERT INTO main.raw_events VALUES "
            "(1, '2026-01-01 00:30:00', 'a'), "
            "(2, '2026-01-01 01:30:00', 'b')",
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T02:00:00",
        audit_sql='SELECT id FROM __ref("orders") WHERE id = 2',
        audit_severity="error",
        audit_run_scope=AuditRunScope.DELTA_AND_FINAL,
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_error_fragment="batch 1",
        expected_audit_count=2,
        expected_row_count=1,
        expected_query_results=(
            (
                "SELECT id, payload FROM main.orders ORDER BY id",
                ((1, "a"),),
            ),
        ),
        expected_delta_retained=True,
    ),
    MicrobatchFailureTestCase(
        description="post_hook failure after multiple successful batches",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        post_hook=[SqlHookEntry(statement="SELECT * FROM nonexistent_table_for_hook")],
        expected_failed_phase=ExecutionPhase.POST_HOOK,
        expected_row_count=3,
    ),
    MicrobatchFailureTestCase(
        description="python post_hook failure after multiple successful batches",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        post_hook=[PythonHookEntry(name="fail_hook", kwargs={"message": "microbatch post failed"})],
        hook_functions=(
            DiscoveredHookFunction(
                file_path=Path(__file__),
                relative_path=Path("hooks/microbatch.py"),
                name="fail_hook",
                function=fail_microbatch_hook,
            ),
        ),
        expected_failed_phase=ExecutionPhase.POST_HOOK,
        expected_error_fragment='post_hooks[0] python("fail_hook") failed: microbatch post failed',
        expected_row_count=3,
    ),
    MicrobatchFailureTestCase(
        description="full-refresh microbatch failure mid-run preserves completed batch data",
        setup_sql=(
            "CREATE TABLE main.raw_events (  id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
            "INSERT INTO main.raw_events VALUES "
            "(1, '2026-01-01 00:30:00', 'a'), "
            "(2, '2026-01-01 01:30:00', 'b')",
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
            "INSERT INTO main.orders VALUES (99, '2025-01-01 00:00:00', 'old')",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T02:00:00",
        is_full_refresh=True,
        cursor_input_relations=(("main.raw_events", "event_time"),),
        audit_sql='SELECT id FROM __ref("orders") WHERE id = 2',
        audit_severity="error",
        audit_run_scope=AuditRunScope.DELTA_AND_FINAL,
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_error_fragment="batch 1",
        expected_audit_count=2,
        expected_row_count=1,
        expected_query_results=(
            (
                "SELECT id, payload FROM main.orders ORDER BY id",
                ((1, "a"),),
            ),
        ),
        expected_delta_retained=True,
    ),
    MicrobatchFailureTestCase(
        description="full-refresh delete_insert fails clearly when output omits cursor",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
        ),
        model_sql=(
            "SELECT DATE_TRUNC('hour', event_time) AS event_hour, COUNT(*) AS event_count "
            "FROM main.raw_events "
            f"WHERE event_time >= '{MICROBATCH_START_SENTINEL}' "
            f"AND event_time < '{MICROBATCH_END_SENTINEL}' "
            "GROUP BY DATE_TRUNC('hour', event_time)"
        ),
        target_schema="main",
        target_name="order_activity",
        incremental_strategy="delete_insert",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        is_full_refresh=True,
        cursor_input_relations=(("main.raw_events", "event_time"),),
        expected_failed_phase=ExecutionPhase.DML,
        expected_error_fragment="microbatch cursor column 'event_time' is not produced",
    ),
    MicrobatchFailureTestCase(
        description="schema change fail rejects before any batch DML in microbatch",
        setup_sql=(
            "CREATE TABLE main.raw_events ("
            "  id INTEGER, event_time TIMESTAMP, payload VARCHAR, extra INTEGER"
            ")",
            "INSERT INTO main.raw_events VALUES (1, '2026-01-01 00:30:00', 'a', 10)",
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
            "INSERT INTO main.orders VALUES (99, '2025-01-01 00:00:00', 'old')",
        ),
        model_sql=(
            "SELECT id, event_time, payload, extra FROM main.raw_events "
            f"WHERE event_time >= '{MICROBATCH_START_SENTINEL}' "
            f"AND event_time < '{MICROBATCH_END_SENTINEL}'"
        ),
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        on_schema_change=OnSchemaChange.FAIL,
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T02:00:00",
        expected_failed_phase=ExecutionPhase.SCHEMA_CHANGE,
        expected_error_fragment="on_schema_change is set to fail",
        expected_row_count=1,
        expected_delta_retained=True,
    ),
    MicrobatchFailureTestCase(
        description="final audit error after all batches reports target already updated",
        setup_sql=(
            _TS_SOURCE_SQL,
            _TS_SOURCE_DATA,
            "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP, payload VARCHAR)",
        ),
        model_sql=_TS_MODEL_SQL,
        target_schema="main",
        target_name="orders",
        incremental_strategy="append",
        cursor_column="event_time",
        cursor_type="timestamp",
        batch_size="1h",
        microbatch_start="2026-01-01T00:00:00",
        microbatch_end="2026-01-01T03:00:00",
        audit_sql='SELECT id FROM __ref("orders") WHERE id > 0',
        audit_severity="error",
        audit_run_scope=AuditRunScope.FINAL,
        expected_failed_phase=ExecutionPhase.AUDIT,
        expected_error_fragment="final audit for 'orders' failed after target update",
        expected_audit_count=1,
        expected_row_count=3,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SUCCESS_TEST_CASES,
    ids=[case.description for case in SUCCESS_TEST_CASES],
)
def test_given_microbatch_model_when_executing_then_succeeds(
    test_case: MicrobatchSuccessTestCase,
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
    FAILURE_TEST_CASES,
    ids=[case.description for case in FAILURE_TEST_CASES],
)
def test_given_microbatch_model_when_execution_fails_then_reports_correct_phase(
    test_case: MicrobatchFailureTestCase,
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
        MicrobatchFailureTestCase(
            description="microbatch executes audits despite accepted origin proof",
            setup_sql=(
                "CREATE TABLE main.orders_origin AS "
                "SELECT NULL::INTEGER AS id, TIMESTAMP '2026-01-01 00:00:00' AS event_time",
                "CREATE TABLE main.raw_events AS "
                "SELECT NULL::INTEGER AS id, TIMESTAMP '2026-01-01 00:30:00' AS event_time",
                "CREATE TABLE main.orders (id INTEGER, event_time TIMESTAMP)",
            ),
            model_sql=(
                "SELECT id, event_time FROM main.raw_events "
                f"WHERE event_time >= '{MICROBATCH_START_SENTINEL}' "
                f"AND event_time < '{MICROBATCH_END_SENTINEL}'"
            ),
            target_schema="main",
            target_name="orders",
            incremental_strategy="append",
            cursor_column="event_time",
            cursor_type="timestamp",
            batch_size="1h",
            microbatch_start="2026-01-01T00:00:00",
            microbatch_end="2026-01-01T01:00:00",
            expected_failed_phase=ExecutionPhase.AUDIT,
            expected_audit_count=1,
            expected_error_fragment="final audit for 'orders' failed after target update",
            expected_row_count=1,
        )
    ],
    ids=["microbatch executes audits despite accepted origin proof"],
)
def test_given_microbatch_with_origin_proof_when_running_then_audit_executes(
    test_case: MicrobatchFailureTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)
    origin_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="main.orders_origin",
        severity="error",
    )
    planned_audit: AuditPlanEntry = build_test_audit_plan_entry(
        name="orders_id_not_null",
        unresolved_sql='SELECT id FROM __ref("orders") WHERE id IS NULL',
        attached_target_name="orders",
        resolved_target_name="main.orders",
        severity="error",
    )
    write_matching_reuse_origin_fingerprint(
        adapter=adapter,
        connection=connection,
        schema="main",
        model_name="orders",
        target_name="orders_origin",
        metadata_json=build_test_audit_gate_metadata(audit=origin_audit),
    )
    entry: ModelPlanEntry = dataclasses.replace(
        build_microbatch_plan_entry(test_case=test_case),
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

    result: ModelExecutionResult = execute_microbatch_entry(
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

    assert result.status == ExecutionStatus.FAILED
    assert result.failed_phase == test_case.expected_failed_phase
    assert result.error_message is not None
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in result.error_message
    assert len(result.audit_results) == test_case.expected_audit_count
    assert result.audit_results[0].reused is False
    assert connection.execute("SELECT COUNT(*) FROM main.orders").fetchone()[0] == 1
