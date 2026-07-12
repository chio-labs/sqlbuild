"""Tests for Python read-side SQL-read Python execution tracking."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.python_nodes.models import PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeStatus
from sqlbuild.executor.python_nodes.helpers.read_side_execution import (
    ReadSidePythonExecutionTracker,
)
from sqlbuild.executor.python_nodes.models import PythonNodeRuntime
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.python_nodes.helpers._test_types import (
    ReadSidePythonTrackerTestCase,
)
from tests.unit.src.sqlbuild.executor.python_nodes.helpers.helpers import (
    PythonNodeContextTestAdapter,
    build_read_side_sql_task_asset_graph,
    read_side_calls,
    reset_read_side_calls,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReadSidePythonTrackerTestCase(
            description="runs sql dependent Python before unrelated SQL completes",
            selected_names=frozenset({"profile_stg_orders", "export_stg_profile"}),
            completed_sql_names=("stg_orders",),
            expected_result_names=("profile_stg_orders", "export_stg_profile"),
            expected_call_order=("profile_stg_orders", "export_stg_profile"),
            expected_statuses=(PythonNodeStatus.SUCCESS, PythonNodeStatus.SUCCESS),
            expected_skip_reasons=(None, None),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_dep_completes_when_tracking_read_side_then_runs_ready_python_nodes(
    test_case: ReadSidePythonTrackerTestCase,
) -> None:
    graph: PythonNodeGraph = build_read_side_sql_task_asset_graph()
    reset_read_side_calls()
    tracker: ReadSidePythonExecutionTracker = ReadSidePythonExecutionTracker(
        python_graph=graph,
        selected_python_names=test_case.selected_names,
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
            default_schema="default_schema",
        ),
    )

    sql_name: str
    for sql_name in test_case.completed_sql_names:
        tracker.record_sql_result(
            ModelExecutionResult(model_name=sql_name, status=ExecutionStatus.SUCCESS)
        )

    assert tuple(result.node_name for result in tracker.results) == test_case.expected_result_names
    assert tuple(result.status for result in tracker.results) == test_case.expected_statuses
    assert (
        tuple(result.skip_reason for result in tracker.results) == test_case.expected_skip_reasons
    )
    assert read_side_calls() == test_case.expected_call_order


@pytest.mark.parametrize(
    "test_case",
    [
        ReadSidePythonTrackerTestCase(
            description="finalizes sql blocked Python nodes as skipped",
            selected_names=frozenset({"profile_stg_orders", "export_stg_profile"}),
            completed_sql_names=(),
            failed_sql_names=("stg_orders",),
            expected_result_names=("export_stg_profile", "profile_stg_orders"),
            expected_call_order=(),
            expected_statuses=(PythonNodeStatus.SKIPPED, PythonNodeStatus.SKIPPED),
            expected_skip_reasons=(
                "Upstream Python node did not complete: profile_stg_orders",
                "Upstream SQL resource did not succeed: stg_orders",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_dep_fails_when_finalizing_read_side_then_skips_unrun_python_nodes(
    test_case: ReadSidePythonTrackerTestCase,
) -> None:
    graph: PythonNodeGraph = build_read_side_sql_task_asset_graph()
    reset_read_side_calls()
    tracker: ReadSidePythonExecutionTracker = ReadSidePythonExecutionTracker(
        python_graph=graph,
        selected_python_names=test_case.selected_names,
        runtime=PythonNodeRuntime(
            adapter=PythonNodeContextTestAdapter(),
            connection_config={},
            connection=object(),
            run_id="test_run",
            target="dev",
            vars={},
            is_reload=False,
            default_schema="default_schema",
        ),
    )

    sql_name: str
    for sql_name in test_case.failed_sql_names:
        tracker.record_sql_result(
            ModelExecutionResult(model_name=sql_name, status=ExecutionStatus.FAILED)
        )
    tracker.finalize_unrun_python_nodes()

    assert tuple(result.node_name for result in tracker.results) == test_case.expected_result_names
    assert tuple(result.status for result in tracker.results) == test_case.expected_statuses
    assert (
        tuple(result.skip_reason for result in tracker.results) == test_case.expected_skip_reasons
    )
    assert read_side_calls() == test_case.expected_call_order
