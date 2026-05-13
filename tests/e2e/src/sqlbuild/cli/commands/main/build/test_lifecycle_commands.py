"""E2E tests for core lifecycle CLI command coverage."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    LifecycleCommandsBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    assert_fragments_in_order,
    prepare_waffle_shop,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        LifecycleCommandsBuildE2ETestCase(
            description="waffle shop core lifecycle commands remain consistent",
            expected_exit_code=0,
            expected_fresh_plan_fragments=(
                "Plan ready (17 selected)",
                "Changed functions (3)",
                "customer_orders",
                "table function",
                "First run (13)",
            ),
            expected_test_fragment="PASS=2  FAIL=0  TOTAL=2",
            expected_audit_fragment="PASS=28  WARN=0  FAIL=0  TOTAL=28",
            expected_run_fragment="Completed successfully.",
            expected_rerun_reasons={
                "stg_orders": "no_change",
                "hourly_order_activity": "normal_incremental",
            },
            expected_full_refresh_fragment="Plan ready (full refresh, 17 selected)",
            expected_plan_ordered_fragments=(
                "Connecting to duckdb...",
                "Connected to duckdb. (<time>)",
                "Inspecting warehouse state...",
                "Generated plan. (<time>)",
                "Plan ready (17 selected)",
                "Changed functions (3)",
                "First run (13)",
                "Seeds (1)",
            ),
            expected_build_ordered_fragments=(
                "Connecting to duckdb...",
                "Connected to duckdb. (<time>)",
                "Inspecting warehouse state...",
                "Generated plan. (<time>)",
                "Plan ready (17 selected)",
                "Execution  sqb build  (concurrency: 1)",
                "Connecting to duckdb...",
                "Connected to duckdb. (<time>)",
                "function  is_completed_order",
                "Completed successfully.",
                "PASS=<n>  WARN=<n>  FAIL=<n>  SKIP=<n>  TOTAL=<n>  (<time>)",
            ),
        )
    ],
    ids=["waffle shop core lifecycle commands remain consistent"],
)
def test_given_waffle_shop_when_running_core_lifecycle_commands_then_outputs_are_consistent(
    test_case: LifecycleCommandsBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)

    fresh_plan: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan"),
        project_dir=project_dir,
    )
    assert fresh_plan.returncode == test_case.expected_exit_code, (
        fresh_plan.stdout + fresh_plan.stderr
    )
    fragment: str
    for fragment in test_case.expected_fresh_plan_fragments:
        assert fragment in fresh_plan.stdout
    assert_fragments_in_order(fresh_plan.stdout, test_case.expected_plan_ordered_fragments)

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == test_case.expected_exit_code, (
        build_result.stdout + build_result.stderr
    )
    assert "PASS=" in build_result.stdout
    assert_fragments_in_order(build_result.stdout, test_case.expected_build_ordered_fragments)

    test_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"),
        project_dir=project_dir,
    )
    assert test_result.returncode == test_case.expected_exit_code, (
        test_result.stdout + test_result.stderr
    )
    assert test_case.expected_test_fragment in test_result.stdout

    audit_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "audit"),
        project_dir=project_dir,
    )
    assert audit_result.returncode == test_case.expected_exit_code, (
        audit_result.stdout + audit_result.stderr
    )
    assert test_case.expected_audit_fragment in audit_result.stdout

    run_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "run"),
        project_dir=project_dir,
    )
    assert run_result.returncode == test_case.expected_exit_code, (
        run_result.stdout + run_result.stderr
    )
    assert test_case.expected_run_fragment in run_result.stdout

    rerun_plan_json: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--json"),
        project_dir=project_dir,
    )
    assert rerun_plan_json.returncode == test_case.expected_exit_code, (
        rerun_plan_json.stdout + rerun_plan_json.stderr
    )
    payload: dict[str, object] = json.loads(rerun_plan_json.stdout)
    reasons_by_name: dict[str, str] = {
        str(entry["name"]): str(entry["reason"]) for entry in payload["models"]
    }
    assert reasons_by_name["stg_orders"] == test_case.expected_rerun_reasons["stg_orders"]
    assert (
        reasons_by_name["hourly_order_activity"]
        == test_case.expected_rerun_reasons["hourly_order_activity"]
    )

    rerun_build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert rerun_build.returncode == test_case.expected_exit_code, (
        rerun_build.stdout + rerun_build.stderr
    )
    assert test_case.expected_run_fragment in rerun_build.stdout

    full_refresh_build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--full-refresh"),
        project_dir=project_dir,
    )
    assert full_refresh_build.returncode == test_case.expected_exit_code, (
        full_refresh_build.stdout + full_refresh_build.stderr
    )
    assert test_case.expected_full_refresh_fragment in full_refresh_build.stdout
