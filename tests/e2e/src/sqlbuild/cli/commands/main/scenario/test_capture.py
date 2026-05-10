"""E2E tests for sqb scenario capture command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.scenario._test_types import (
    ScenarioCliE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    assert_scenario_snapshot,
    build_scenario_project_files,
    list_scenario_relation_names,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCliE2ETestCase(
            description="captures multiple selected scenarios by name and path",
            command=(
                "--no-color",
                "scenario",
                "capture",
                "order_totals_pass",
                "tests/scenarios/nested/orders_assert_pass.sql",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Execution  sqb scenario capture",
                "Scenario Capture (2 selected)",
                "order_totals_pass",
                "orders_assert_pass",
                "1 relation, 2 rows",
                "1 relation, 1 row",
                "snapshot",
                "PASS=2  FAIL=0  TOTAL=2",
            ),
            expected_retained_prefix_count=0,
        ),
    ],
    ids=["captures multiple selected scenarios by name and path"],
)
def test_given_selected_scenarios_when_running_capture_then_writes_snapshots(
    test_case: ScenarioCliE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="scenario_project",
        repo_files=build_scenario_project_files(),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    retained_names: tuple[str, ...] = list_scenario_relation_names(
        db_path=project_dir / "scenario_demo.duckdb"
    )
    assert len(retained_names) == test_case.expected_retained_prefix_count
    assert_scenario_snapshot(
        project_dir=project_dir,
        scenario_name="order_totals_pass",
        expected_row_count=2,
    )
    assert_scenario_snapshot(
        project_dir=project_dir,
        scenario_name="orders_assert_pass",
        expected_row_count=1,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCliE2ETestCase(
            description="captures scenario folder selector and retains materialized input",
            command=("--no-color", "scenario", "capture", "nested", "--retain"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Scenario Capture (1 selected)",
                "orders_assert_pass",
                "1 relation, 1 row",
                "Retained relations:",
                "raw_orders -> main.__sqb_",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            expected_retained_prefix_count=1,
        ),
    ],
    ids=["captures scenario folder selector and retains materialized input"],
)
def test_given_folder_selector_when_running_capture_with_retain_then_keeps_input_artifacts(
    test_case: ScenarioCliE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="scenario_project",
        repo_files=build_scenario_project_files(),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    retained_names: tuple[str, ...] = list_scenario_relation_names(
        db_path=project_dir / "scenario_demo.duckdb"
    )
    assert len(retained_names) == test_case.expected_retained_prefix_count
    assert retained_names[0].endswith("__source__raw_orders")
    assert_scenario_snapshot(
        project_dir=project_dir,
        scenario_name="orders_assert_pass",
        expected_row_count=1,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCliE2ETestCase(
            description="capture applies local type overrides from project config",
            command=("--no-color", "scenario", "capture", "order_totals_pass"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Scenario Capture (1 selected)",
                "order_totals_pass",
                "1 relation, 2 rows",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            expected_retained_prefix_count=0,
        ),
    ],
    ids=["capture applies local type overrides from project config"],
)
def test_given_local_type_override_when_running_capture_then_manifest_uses_override(
    test_case: ScenarioCliE2ETestCase,
    tmp_path: Path,
) -> None:
    repo_files: dict[str, str] = build_scenario_project_files()
    repo_files["sqlbuild_project.toml"] += (
        "\n[scenario.local_type_overrides.duckdb]\n"
        '"INTEGER" = "BIGINT"\n'
        '"DECIMAL(*,0)" = "BIGINT"\n'
        '"DECIMAL(*,*)" = "DECIMAL({1}, {2})"\n'
    )
    repo_files["tests/scenarios/order_totals_pass.sql"] = (
        'SCENARIO (description: "Order totals scenario", tags: ["scenario"]);\n\n'
        "WITH\n"
        "__source__raw_orders AS (\n"
        "  SELECT\n"
        "    CAST(1 AS INTEGER) AS id,\n"
        "    CAST(10 AS DECIMAL(12,0)) AS amount,\n"
        "    CAST(1.25 AS DECIMAL(8,2)) AS tax\n"
        "  UNION ALL\n"
        "  SELECT\n"
        "    CAST(2 AS INTEGER) AS id,\n"
        "    CAST(5 AS DECIMAL(12,0)) AS amount,\n"
        "    CAST(0.75 AS DECIMAL(8,2)) AS tax\n"
        "),\n"
        "__expected__order_totals AS (\n"
        "  SELECT 15 AS total_amount\n"
        ")\n"
        "SELECT 1\n"
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="scenario_project",
        repo_files=repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    assert_scenario_snapshot(
        project_dir=project_dir,
        scenario_name="order_totals_pass",
        expected_row_count=2,
        expected_local_types={"id": "BIGINT", "amount": "BIGINT", "tax": "DECIMAL(8, 2)"},
    )
