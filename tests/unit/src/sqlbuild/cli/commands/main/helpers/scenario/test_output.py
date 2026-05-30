from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.helpers.scenario.capture import _write_capture_result
from sqlbuild.cli.commands.main.helpers.scenario.runner import _write_scenario_result
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.models import (
    ScenarioExpectedCheckExecutionResult,
    ScenarioRunResult,
    ScenarioSnapshotCaptureRelationResult,
    ScenarioSnapshotCaptureResult,
    ScenarioSnapshotCaptureRunResult,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from tests.unit.src.sqlbuild.cli.commands.main.helpers.scenario._test_types import (
    ScenarioCaptureOutputTestCase,
    ScenarioRunOutputTestCase,
)

SCENARIO_RUN_OUTPUT_TEST_CASES: tuple[ScenarioRunOutputTestCase, ...] = (
    ScenarioRunOutputTestCase(
        description="styles scenario and check statuses semantically",
        expected_fragments=(
            "orders_paid",
            "\033[32mPASS\033[0m",
            "expected fact_orders",
            "\033[31mFAIL\033[0m  2 mismatched",
        ),
    ),
    ScenarioRunOutputTestCase(
        description="leaves no-color scenario output plain",
        expected_fragments=("orders_paid", "PASS", "FAIL  2 mismatched"),
        unexpected_fragments=("\033[",),
    ),
)

SCENARIO_CAPTURE_OUTPUT_TEST_CASES: tuple[ScenarioCaptureOutputTestCase, ...] = (
    ScenarioCaptureOutputTestCase(
        description="styles capture result and relation statuses semantically",
        expected_fragments=(
            "orders_paid",
            "\033[32mPASS\033[0m",
            "source   raw__orders",
            "\033[31mFAIL\033[0m  4 rows, 128 B",
        ),
    ),
    ScenarioCaptureOutputTestCase(
        description="leaves no-color capture output plain",
        expected_fragments=("orders_paid", "PASS", "source   raw__orders", "FAIL  4 rows"),
        unexpected_fragments=("\033[",),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    SCENARIO_RUN_OUTPUT_TEST_CASES,
    ids=[case.description for case in SCENARIO_RUN_OUTPUT_TEST_CASES],
)
def test_given_scenario_result_when_writing_output_then_styles_statuses(
    test_case: ScenarioRunOutputTestCase,
) -> None:
    stream: StringIO = StringIO()
    _write_scenario_result(
        result=ScenarioRunResult(
            scenario_name="orders_paid",
            status=ExecutionStatus.SUCCESS,
            expected_results=(
                ScenarioExpectedCheckExecutionResult(
                    scenario_name="orders_paid",
                    model_name="fact_orders",
                    status=ExecutionStatus.FAILED,
                    mismatched_row_count=2,
                ),
            ),
        ),
        stream=stream,
        use_color="\033[" not in test_case.unexpected_fragments,
    )

    output: str = stream.getvalue()
    for fragment in test_case.expected_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output


@pytest.mark.parametrize(
    "test_case",
    SCENARIO_CAPTURE_OUTPUT_TEST_CASES,
    ids=[case.description for case in SCENARIO_CAPTURE_OUTPUT_TEST_CASES],
)
def test_given_scenario_capture_result_when_writing_output_then_styles_statuses(
    test_case: ScenarioCaptureOutputTestCase,
) -> None:
    stream: StringIO = StringIO()
    output_path: Path = Path(__file__)
    _write_capture_result(
        result=ScenarioSnapshotCaptureRunResult(
            scenario_name="orders_paid",
            status=ExecutionStatus.SUCCESS,
            capture_result=ScenarioSnapshotCaptureResult(
                scenario_name="orders_paid",
                status=ExecutionStatus.SUCCESS,
                manifest_path=output_path,
                relation_results=(
                    ScenarioSnapshotCaptureRelationResult(
                        kind=ScenarioArtifactKind.SOURCE,
                        logical_name="raw__orders",
                        source_relation="raw.orders",
                        file_path=output_path,
                        status=ExecutionStatus.FAILED,
                        row_count=4,
                        byte_count=128,
                    ),
                ),
            ),
        ),
        scenario_plan=None,
        project_dir=output_path.parent,
        stream=stream,
        use_color="\033[" not in test_case.unexpected_fragments,
    )

    output: str = stream.getvalue()
    for fragment in test_case.expected_fragments:
        assert fragment in output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in output
