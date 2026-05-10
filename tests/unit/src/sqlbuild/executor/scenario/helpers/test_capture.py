from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.planner.models import ScenarioExecutionPlan
from sqlbuild.executor.scenario.helpers.capture import execute_scenario_snapshot_capture_steps
from sqlbuild.executor.scenario.models import ScenarioSnapshotCaptureRunResult
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.unit.src.sqlbuild.executor.scenario.helpers._test_types import (
    ExecuteScenarioSnapshotCaptureStepsTestCase,
)
from tests.unit.src.sqlbuild.executor.scenario.helpers.helpers import assert_capture_steps_error
from tests.unit.src.sqlbuild.executor.scenario.main.helpers import (
    ScenarioSnapshotCaptureStepsTestAdapter,
    build_scenario_cleanup_test_plan_with_project_seed,
)

SCENARIO_PLAN: ScenarioExecutionPlan = build_scenario_cleanup_test_plan_with_project_seed()

CAPTURE_STEPS_TEST_CASES: list[ExecuteScenarioSnapshotCaptureStepsTestCase] = [
    ExecuteScenarioSnapshotCaptureStepsTestCase(
        description="captures inputs and cleans up by default",
        retain=False,
        fail_on_create_target=None,
        fail_on_seed=False,
        fail_on_query_target=None,
        expected_status=ExecutionStatus.SUCCESS,
        expected_retained=False,
        expected_fixture_result_count=2,
        expected_seed_result_count=1,
        expected_has_capture_result=True,
        expected_has_cleanup_result=True,
    ),
    ExecuteScenarioSnapshotCaptureStepsTestCase(
        description="retain skips final cleanup",
        retain=True,
        fail_on_create_target=None,
        fail_on_seed=False,
        fail_on_query_target=None,
        expected_status=ExecutionStatus.SUCCESS,
        expected_retained=True,
        expected_fixture_result_count=2,
        expected_seed_result_count=1,
        expected_has_capture_result=True,
        expected_has_cleanup_result=False,
    ),
    ExecuteScenarioSnapshotCaptureStepsTestCase(
        description="fixture failure skips capture and cleans up",
        retain=False,
        fail_on_create_target="raw__orders",
        fail_on_seed=False,
        fail_on_query_target=None,
        expected_status=ExecutionStatus.FAILED,
        expected_retained=False,
        expected_fixture_result_count=1,
        expected_seed_result_count=0,
        expected_has_capture_result=False,
        expected_has_cleanup_result=True,
        expected_error_fragment="fixture create failed",
    ),
    ExecuteScenarioSnapshotCaptureStepsTestCase(
        description="seed failure skips capture and cleans up",
        retain=False,
        fail_on_create_target=None,
        fail_on_seed=True,
        fail_on_query_target=None,
        expected_status=ExecutionStatus.FAILED,
        expected_retained=False,
        expected_fixture_result_count=2,
        expected_seed_result_count=1,
        expected_has_capture_result=False,
        expected_has_cleanup_result=True,
        expected_error_fragment="seed load failed",
    ),
    ExecuteScenarioSnapshotCaptureStepsTestCase(
        description="capture failure returns failed capture result and cleans up",
        retain=False,
        fail_on_create_target=None,
        fail_on_seed=False,
        fail_on_query_target="stg_customers",
        expected_status=ExecutionStatus.FAILED,
        expected_retained=False,
        expected_fixture_result_count=2,
        expected_seed_result_count=1,
        expected_has_capture_result=True,
        expected_has_cleanup_result=True,
        expected_error_fragment="warehouse read failed",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CAPTURE_STEPS_TEST_CASES,
    ids=[case.description for case in CAPTURE_STEPS_TEST_CASES],
)
def test_given_scenario_plan_when_executing_snapshot_capture_steps_then_returns_expected_result(
    tmp_path: Path,
    test_case: ExecuteScenarioSnapshotCaptureStepsTestCase,
) -> None:
    adapter: ScenarioSnapshotCaptureStepsTestAdapter = ScenarioSnapshotCaptureStepsTestAdapter(
        fail_on_create_target=test_case.fail_on_create_target,
        fail_on_seed=test_case.fail_on_seed,
        fail_on_query_target=test_case.fail_on_query_target,
    )

    result: ScenarioSnapshotCaptureRunResult = execute_scenario_snapshot_capture_steps(
        project_dir=tmp_path,
        scenario_plan=SCENARIO_PLAN,
        adapter=adapter,
        connection=object(),
        captured_at="2026-05-09T00:00:00Z",
        capture_adapter="duckdb",
        capture_dialect="duckdb",
        sqlbuild_version="0.1.0",
        retain=test_case.retain,
    )

    assert result.status == test_case.expected_status
    assert result.retained is test_case.expected_retained
    assert len(result.fixture_results) == test_case.expected_fixture_result_count
    assert len(result.seed_results) == test_case.expected_seed_result_count
    assert (result.capture_result is not None) is test_case.expected_has_capture_result
    assert (result.cleanup_result is not None) is test_case.expected_has_cleanup_result
    assert_capture_steps_error(result=result, test_case=test_case)
