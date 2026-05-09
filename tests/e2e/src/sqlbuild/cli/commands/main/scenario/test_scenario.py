"""E2E tests for sqb scenario test command."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.scenario._test_types import (
    ScenarioCliE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    build_scenario_project_files,
    list_scenario_relation_names,
    scenario_relation_name_by_suffix,
    scenario_relation_row_count,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    prepare_waffle_shop,
    run_sqb,
)

SCENARIO_CLI_TEST_CASES: list[ScenarioCliE2ETestCase] = [
    ScenarioCliE2ETestCase(
        description="runs selected scenario by name and cleans up artifacts",
        command=("--no-color", "scenario", "test", "order_totals_pass"),
        expected_exit_code=0,
        expected_stdout_fragments=(
            "Execution  sqb scenario test  (target: order_totals_pass, concurrency: 1)",
            "Scenario (1 selected)",
            "order_totals_pass",
            "check     expected order_totals",
            "PASS=1  FAIL=0  TOTAL=1",
        ),
        expected_retained_prefix_count=0,
    ),
    ScenarioCliE2ETestCase(
        description="runs assertion scenario and reports passing assertion check",
        command=("--no-color", "scenario", "test", "orders_assert_pass"),
        expected_exit_code=0,
        expected_stdout_fragments=(
            "Scenario (1 selected)",
            "orders_assert_pass",
            "check     assertion no_negative_orders",
            "PASS=1  FAIL=0  TOTAL=1",
        ),
        expected_retained_prefix_count=0,
    ),
    ScenarioCliE2ETestCase(
        description="runs selected scenario by path and cleans up artifacts",
        command=(
            "--no-color",
            "scenario",
            "test",
            "tests/scenarios/nested/orders_assert_pass.sql",
        ),
        expected_exit_code=0,
        expected_stdout_fragments=(
            "Scenario (1 selected)",
            "orders_assert_pass",
            "check     assertion no_negative_orders",
            "PASS=1  FAIL=0  TOTAL=1",
        ),
        expected_retained_prefix_count=0,
    ),
    ScenarioCliE2ETestCase(
        description="retains artifacts and prints relation map",
        command=("--no-color", "scenario", "test", "order_totals_pass", "--retain"),
        expected_exit_code=0,
        expected_stdout_fragments=(
            "Scenario (1 selected)",
            "order_totals_pass",
            "Retained relations:",
            "check     expected order_totals",
            "source raw_orders -> __sqb_",
            "model  orders -> __sqb_",
            "model  order_totals -> __sqb_",
            "PASS=1  FAIL=0  TOTAL=1",
        ),
        expected_retained_prefix_count=3,
    ),
    ScenarioCliE2ETestCase(
        description="failed scenario suggests retain after cleanup",
        command=("--no-color", "scenario", "test", "order_totals_fail"),
        expected_exit_code=1,
        expected_stdout_fragments=(
            "Scenario (1 selected)",
            "order_totals_fail",
            "check     expected order_totals",
            "expected order_totals:",
            "Rerun with --retain to inspect scenario-owned artifacts.",
            "PASS=0  FAIL=1  TOTAL=1",
        ),
        expected_retained_prefix_count=0,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SCENARIO_CLI_TEST_CASES,
    ids=[case.description for case in SCENARIO_CLI_TEST_CASES],
)
def test_given_scenario_project_when_running_scenario_test_then_cli_behaves_as_expected(
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
    assert test_case.expected_retained_prefix_count is not None
    retained_names: tuple[str, ...] = list_scenario_relation_names(
        db_path=project_dir / "scenario_demo.duckdb"
    )
    assert len(retained_names) == test_case.expected_retained_prefix_count


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCliE2ETestCase(
            description="runs all discovered scenarios",
            command=("--no-color", "scenario", "test"),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "Scenario (3 selected)",
                "order_totals_pass",
                "orders_assert_pass",
                "order_totals_fail",
                "check     expected order_totals",
                "check     assertion no_negative_orders",
                "PASS=2  FAIL=1  TOTAL=3",
            ),
            expected_retained_prefix_count=0,
        )
    ],
    ids=["runs all discovered scenarios"],
)
def test_given_multiple_scenarios_when_running_without_selector_then_runs_all_scenarios(
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


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCliE2ETestCase(
            description="unknown selector fails clearly",
            command=("--no-color", "scenario", "test", "missing_scenario"),
            expected_exit_code=1,
            expected_stderr_fragments=("Unknown scenario selector 'missing_scenario'",),
        )
    ],
    ids=["unknown selector fails clearly"],
)
def test_given_unknown_scenario_selector_when_running_scenario_test_then_fails_clearly(
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
    expected_stderr_fragment: str
    for expected_stderr_fragment in test_case.expected_stderr_fragments:
        assert expected_stderr_fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCliE2ETestCase(
            description="waffle shop fixture scenarios pass on duckdb",
            command=("--no-color", "scenario", "test"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Scenario (3 selected)",
                "Connecting to duckdb...",
                "Running scenarios...",
                "daily_revenue_minimal",
                "check     expected daily_revenue",
                "check     assertion no_negative_revenue",
                "daily_revenue_multi_order",
                "check     assertion positive_average_order_value",
                "fact_order_retained_artifacts",
                "check     expected scenario_order_prices",
                "check     assertion positive_line_total",
                "PASS=3  FAIL=0  TOTAL=3",
            ),
            expected_retained_prefix_count=0,
        )
    ],
    ids=["waffle shop fixture scenarios pass on duckdb"],
)
def test_given_waffle_shop_fixture_when_running_scenario_test_then_scenarios_pass_on_duckdb(
    test_case: ScenarioCliE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    retained_names: tuple[str, ...] = list_scenario_relation_names(
        db_path=project_dir / "waffle_shop.duckdb"
    )
    assert len(retained_names) == test_case.expected_retained_prefix_count


@pytest.mark.parametrize(
    "test_case",
    [
        ScenarioCliE2ETestCase(
            description="waffle shop fixture retain keeps scenario artifacts on duckdb",
            command=(
                "--no-color",
                "scenario",
                "test",
                "fact_order_retained_artifacts",
                "--retain",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "fact_order_retained_artifacts",
                "check     expected scenario_order_prices",
                "check     assertion positive_line_total",
                "Retained relations:",
                "source raw_orders -> __sqb_",
                "ref    stg_payments -> __sqb_",
                "seed   waffle_types -> __sqb_",
                "model  scenario_order_prices -> __sqb_",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            expected_retained_prefix_count=4,
        )
    ],
    ids=["waffle shop fixture retain keeps scenario artifacts on duckdb"],
)
def test_given_waffle_shop_fixture_when_running_with_retain_then_keeps_scenario_artifacts(
    test_case: ScenarioCliE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    retained_names: tuple[str, ...] = list_scenario_relation_names(
        db_path=project_dir / "waffle_shop.duckdb"
    )
    assert len(retained_names) == test_case.expected_retained_prefix_count
    expected_suffix: str
    for expected_suffix in (
        "__source__raw_orders",
        "__ref__stg_payments",
        "__seed__waffle_types",
        "__model__scenario_order_prices",
    ):
        retained_relation_name: str = scenario_relation_name_by_suffix(
            db_path=project_dir / "waffle_shop.duckdb",
            suffix=expected_suffix,
        )
        assert (
            scenario_relation_row_count(
                db_path=project_dir / "waffle_shop.duckdb",
                relation_name=retained_relation_name,
            )
            == 1
        )
