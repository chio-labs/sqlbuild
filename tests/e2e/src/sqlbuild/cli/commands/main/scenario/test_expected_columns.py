"""E2E tests for scenario expected CTEs whose columns differ from their model's output."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.scenario._test_types import (
    ScenarioExpectedColumnsE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    build_expected_columns_scenario_project_files,
    selected_fields,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    (
        ScenarioExpectedColumnsE2ETestCase(
            description="complete expected output compares every column",
            expected_sql="SELECT 'o1' AS order_id, 'placed' AS status, FALSE AS is_cancelled",
            expected_exit_code=0,
            expected_stdout_fragments=("PASS=1  FAIL=0  TOTAL=1",),
            expected_json_results=(
                {
                    "model_name": "order_flags",
                    "status": "success",
                    "comparison_status": "completed",
                    "actual_row_count": 1,
                    "expected_row_count": 1,
                    "mismatched_row_count": 0,
                },
            ),
        ),
        ScenarioExpectedColumnsE2ETestCase(
            description="expected output missing a model column is rejected before execution",
            expected_sql="SELECT 'o1' AS order_id, 'placed' AS status",
            expected_exit_code=1,
            expected_stdout_fragments=(
                "error[S512]",
                "expected output __expected__order_flags does not list columns that model "
                "'order_flags' outputs: is_cancelled",
            ),
            unexpected_stdout_fragments=("X504", "mismatched", "actual="),
        ),
        ScenarioExpectedColumnsE2ETestCase(
            description="expected output listing a column the model lacks is rejected",
            expected_sql=(
                "SELECT 'o1' AS order_id, 'placed' AS status, FALSE AS is_cancelled, "
                "1 AS line_count"
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "error[S512]",
                "lists columns that model 'order_flags' does not output: line_count",
            ),
            unexpected_stdout_fragments=("X504", "mismatched"),
        ),
        ScenarioExpectedColumnsE2ETestCase(
            description="comparison that fails to run reports its error without counts",
            expected_sql=(
                "SELECT 'o1' AS order_id, 'placed' AS status, "
                "CAST('maybe' AS BOOLEAN) AS is_cancelled"
            ),
            expected_exit_code=1,
            expected_stdout_fragments=("expected order_flags", "ERROR", "error[X504]"),
            unexpected_stdout_fragments=("mismatched", "actual="),
            expected_json_results=(
                {
                    "model_name": "order_flags",
                    "status": "failed",
                    "comparison_status": "not_run",
                    "actual_row_count": None,
                    "expected_row_count": None,
                    "mismatched_row_count": None,
                    "error_code": "X504",
                },
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_scenario_expected_columns_when_testing_then_comparison_is_reported_honestly(
    test_case: ScenarioExpectedColumnsE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="scenario_expected_columns",
        repo_files=build_expected_columns_scenario_project_files(
            expected_sql=test_case.expected_sql
        ),
    )

    text: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "scenario", "test"), project_dir=project_dir
    )
    structured: subprocess.CompletedProcess[str] = run_sqb(
        command=("scenario", "test", "--json"), project_dir=project_dir
    )

    assert text.returncode == test_case.expected_exit_code, text.stdout + text.stderr
    assert structured.returncode == test_case.expected_exit_code, structured.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in text.stdout, text.stdout
    for fragment in test_case.unexpected_stdout_fragments:
        assert fragment not in text.stdout, text.stdout
    payload: dict[str, Any] = json.loads(structured.stdout)
    results: list[dict[str, Any]] = payload["checks"][0]["expected_results"]
    assert len(results) == len(test_case.expected_json_results), results
    assert (
        tuple(map(selected_fields, results, test_case.expected_json_results))
        == test_case.expected_json_results
    )
