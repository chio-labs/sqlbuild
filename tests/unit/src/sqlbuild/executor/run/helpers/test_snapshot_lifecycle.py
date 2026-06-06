"""Tests for snapshot execution lifecycle side effects."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.adapters.snowflake.client import SnowflakeAdapter
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.run.helpers.snapshot import (
    _apply_snapshot_schema_change,
    execute_snapshot_entry,
)
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.models import SqlHookEntry
from sqlbuild.spec.models.project import SnapshotsConfig
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import (
    SnapshotLifecycleTestCase,
    SnapshotRuntimeContractErrorTestCase,
    SnapshotSchemaChangeTestCase,
)
from tests.unit.src.sqlbuild.executor.run.helpers.helpers import build_snapshot_execution_plan_entry

COMPATIBLE_SNOWFLAKE_SNAPSHOT_SCHEMA_CHANGE_TEST_CASES: list[SnapshotSchemaChangeTestCase] = [
    SnapshotSchemaChangeTestCase(
        description="snowflake timestamp alias is not a snapshot type change",
        target_columns=(ColumnInfo(name="updated_at", type="TIMESTAMP"),),
        delta_columns=(ColumnInfo(name="updated_at", type="TIMESTAMP_NTZ"),),
        expected_valid=True,
    ),
    SnapshotSchemaChangeTestCase(
        description="snowflake narrower varchar delta is not a snapshot type change",
        target_columns=(ColumnInfo(name="plan", type="VARCHAR(5)"),),
        delta_columns=(ColumnInfo(name="plan", type="VARCHAR(3)"),),
        expected_valid=True,
    ),
]

INCOMPATIBLE_SNOWFLAKE_SNAPSHOT_SCHEMA_CHANGE_TEST_CASES: list[SnapshotSchemaChangeTestCase] = [
    SnapshotSchemaChangeTestCase(
        description="snowflake timestamp time zone variant remains a type change",
        target_columns=(ColumnInfo(name="updated_at", type="TIMESTAMP_NTZ"),),
        delta_columns=(ColumnInfo(name="updated_at", type="TIMESTAMP_TZ"),),
        expected_valid=False,
        expected_error_fragment="type changes: updated_at",
    ),
    SnapshotSchemaChangeTestCase(
        description="snowflake wider varchar delta remains a type change",
        target_columns=(ColumnInfo(name="plan", type="VARCHAR(3)"),),
        delta_columns=(ColumnInfo(name="plan", type="VARCHAR(5)"),),
        expected_valid=False,
        expected_error_fragment="type changes: plan",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotLifecycleTestCase(
            description="successful snapshot runs hooks writes fingerprint and cleans delta",
            run_id="snapshot_lifecycle_run",
            pre_hook=(
                SqlHookEntry(statement="CREATE TABLE main.snapshot_hook_log (phase VARCHAR)"),
                SqlHookEntry(statement="INSERT INTO main.snapshot_hook_log VALUES ('pre')"),
            ),
            post_hook=(
                SqlHookEntry(statement="INSERT INTO main.snapshot_hook_log VALUES ('post')"),
            ),
            expected_hook_events=(
                "CREATE TABLE main.snapshot_hook_log (phase VARCHAR)",
                "INSERT INTO main.snapshot_hook_log VALUES ('pre')",
                "INSERT INTO main.snapshot_hook_log VALUES ('post')",
            ),
            expected_model_name="customer_snapshot",
            expected_target_name="customer_snapshot",
        )
    ],
    ids=["successful snapshot runs hooks writes fingerprint and cleans delta"],
)
def test_given_successful_snapshot_when_executing_then_runs_lifecycle_side_effects(
    test_case: SnapshotLifecycleTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    entry: ModelPlanEntry = build_snapshot_execution_plan_entry(
        pre_hooks=test_case.pre_hook,
        post_hooks=test_case.post_hook,
    )

    result: ModelExecutionResult = execute_snapshot_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_targets={},
        seed_targets={},
        source_map={},
        model_audits=(),
        run_id=test_case.run_id,
        query_change_tracking=True,
    )
    hook_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute("SELECT phase FROM main.snapshot_hook_log").fetchall()
    )
    fingerprint_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute(
            f"SELECT model_name, target_name, run_id FROM main.{FINGERPRINT_TABLE_NAME}"
        ).fetchall()
    )
    lifecycle_sql: tuple[str, ...] = tuple(event.content for event in result.lifecycle_events)

    assert result.status == ExecutionStatus.SUCCESS
    assert hook_rows == (("pre",), ("post",))
    assert fingerprint_rows == (
        (test_case.expected_model_name, test_case.expected_target_name, test_case.run_id),
    )
    assert (
        adapter.relation_exists(
            connection,
            database=None,
            schema="main",
            name="customer_snapshot__snapshot_delta",
        )
        is False
    )
    expected_hook_event: str
    for expected_hook_event in test_case.expected_hook_events:
        assert expected_hook_event in lifecycle_sql

    adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    COMPATIBLE_SNOWFLAKE_SNAPSHOT_SCHEMA_CHANGE_TEST_CASES,
    ids=[case.description for case in COMPATIBLE_SNOWFLAKE_SNAPSHOT_SCHEMA_CHANGE_TEST_CASES],
)
def test_given_snapshot_schema_change_when_checking_compatible_snowflake_types_then_it_is_valid(
    test_case: SnapshotSchemaChangeTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    entry: ModelPlanEntry = build_snapshot_execution_plan_entry()

    _apply_snapshot_schema_change(
        adapter=adapter,
        connection=object(),
        entry=entry,
        snapshots=SnapshotsConfig(),
        target_qualified="analytics.customer_snapshot",
        target_columns=test_case.target_columns,
        delta_columns=test_case.delta_columns,
        allow_snapshot_schema_change=False,
        statement_recorder=StatementRecorder(),
    )

    assert test_case.expected_valid is True


@pytest.mark.parametrize(
    "test_case",
    INCOMPATIBLE_SNOWFLAKE_SNAPSHOT_SCHEMA_CHANGE_TEST_CASES,
    ids=[case.description for case in INCOMPATIBLE_SNOWFLAKE_SNAPSHOT_SCHEMA_CHANGE_TEST_CASES],
)
def test_given_snapshot_schema_change_when_checking_incompatible_snowflake_types_then_it_raises(
    test_case: SnapshotSchemaChangeTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    entry: ModelPlanEntry = build_snapshot_execution_plan_entry()

    with pytest.raises(ExecutorInputError, match=test_case.expected_error_fragment):
        _apply_snapshot_schema_change(
            adapter=adapter,
            connection=object(),
            entry=entry,
            snapshots=SnapshotsConfig(),
            target_qualified="analytics.customer_snapshot",
            target_columns=test_case.target_columns,
            delta_columns=test_case.delta_columns,
            allow_snapshot_schema_change=False,
            statement_recorder=StatementRecorder(),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotRuntimeContractErrorTestCase(
            description="snapshot delta has extra runtime column",
            contract_columns=(
                ColumnInfo(name="customer_id", type="INTEGER"),
                ColumnInfo(name="updated_at", type="TIMESTAMP"),
            ),
            run_id="runtime_contract_failure",
            expected_error_fragment="runtime contract has extra columns: plan",
        )
    ],
    ids=["snapshot delta has extra runtime column"],
)
def test_given_snapshot_contract_violation_when_executing_then_fails_before_target_update(
    test_case: SnapshotRuntimeContractErrorTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    entry: ModelPlanEntry = build_snapshot_execution_plan_entry(
        contract_enforced=True,
        contract_columns=test_case.contract_columns,
    )

    result: ModelExecutionResult = execute_snapshot_entry(
        entry=entry,
        adapter=adapter,
        connection=connection,
        model_targets={},
        seed_targets={},
        source_map={},
        model_audits=(),
        run_id=test_case.run_id,
        query_change_tracking=True,
    )

    assert result.status == ExecutionStatus.FAILED
    assert test_case.expected_error_fragment in (result.error_message or "")
    assert (
        adapter.relation_exists(
            connection,
            database=None,
            schema="main",
            name="customer_snapshot",
        )
        is False
    )

    adapter.close(connection)
