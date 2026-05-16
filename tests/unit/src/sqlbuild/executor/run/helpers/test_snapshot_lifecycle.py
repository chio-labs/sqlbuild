"""Tests for snapshot execution lifecycle side effects."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.run.helpers.snapshot import execute_snapshot_entry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import SnapshotLifecycleTestCase
from tests.unit.src.sqlbuild.executor.run.helpers.helpers import build_snapshot_execution_plan_entry


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotLifecycleTestCase(
            description="successful snapshot runs hooks writes fingerprint and cleans delta",
            run_id="snapshot_lifecycle_run",
            pre_hook=(
                "CREATE TABLE main.snapshot_hook_log (phase VARCHAR)",
                "INSERT INTO main.snapshot_hook_log VALUES ('pre')",
            ),
            post_hook=("INSERT INTO main.snapshot_hook_log VALUES ('post')",),
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
        pre_hook=test_case.pre_hook,
        post_hook=test_case.post_hook,
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
