from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.playground import run_playground
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import skip_unless_dbt_is_runnable
from tests.e2e.src.sqlbuild.cli.commands.main.playground._test_types import (
    DbtChangeAwarePlaygroundLifecycleTestCase,
    PythonNodesPlaygroundLifecycleTestCase,
    VirtualPlaygroundLifecycleTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualPlaygroundLifecycleTestCase(
            description="virtual playground runs state build branch and promote lifecycle",
            project_name="virtual_waffle_shop",
            expected_build_fragments=(
                "Virtual State Initialized",
                "Seeds (1)",
                "waffle_price_tiers",
                "Completed successfully.",
            ),
            expected_test_fragments=(
                "Test (1 selected",
                "test_fact_waffle_orders",
                "PASS=1",
            ),
            expected_audit_fragments=(
                "Audit (3 selected",
                "not_null (order_id)",
                "unique (order_id)",
                "PASS=3",
            ),
            expected_scenario_fragments=(
                "Scenario",
                "customer_revenue_minimal",
                "PASS=1",
            ),
            expected_branch_fragments=(
                "Virtual environment",
                "name: pr",
                "Completed successfully.",
            ),
            expected_diff_fragments=(
                "Virtual diff",
                "No schema differences",
            ),
            expected_promote_fragments=(
                "Virtual promotion complete",
                "pr -> dev",
            ),
        )
    ],
    ids=["virtual playground runs state build branch and promote lifecycle"],
)
def test_given_virtual_playground_when_running_lifecycle_then_it_succeeds(
    test_case: VirtualPlaygroundLifecycleTestCase,
    tmp_path: Path,
) -> None:
    assert run_playground(tmp_path, test_case.project_name, template="virtual") == 0
    project_dir: Path = tmp_path / test_case.project_name

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("state", "init"), project_dir=project_dir
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    test_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"), project_dir=project_dir
    )
    audit_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "audit"), project_dir=project_dir
    )
    scenario_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "scenario", "test"), project_dir=project_dir
    )
    branch_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    diff_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "diff", "dev:pr", "--schema-only"),
        project_dir=project_dir,
    )
    promote_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
        project_dir=project_dir,
    )

    build_output: str = (
        init_result.stdout + init_result.stderr + build_result.stdout + build_result.stderr
    )
    assert init_result.returncode == 0
    assert build_result.returncode == 0
    expected_fragment: str
    for expected_fragment in test_case.expected_build_fragments:
        assert expected_fragment in build_output

    test_output: str = test_result.stdout + test_result.stderr
    assert test_result.returncode == 0
    for expected_fragment in test_case.expected_test_fragments:
        assert expected_fragment in test_output

    audit_output: str = audit_result.stdout + audit_result.stderr
    assert audit_result.returncode == 0
    for expected_fragment in test_case.expected_audit_fragments:
        assert expected_fragment in audit_output

    scenario_output: str = scenario_result.stdout + scenario_result.stderr
    assert scenario_result.returncode == 0
    for expected_fragment in test_case.expected_scenario_fragments:
        assert expected_fragment in scenario_output

    branch_output: str = branch_result.stdout + branch_result.stderr
    assert branch_result.returncode == 0
    for expected_fragment in test_case.expected_branch_fragments:
        assert expected_fragment in branch_output

    diff_output: str = diff_result.stdout + diff_result.stderr
    assert diff_result.returncode == 0
    for expected_fragment in test_case.expected_diff_fragments:
        assert expected_fragment in diff_output

    promote_output: str = promote_result.stdout + promote_result.stderr
    assert promote_result.returncode == 0
    for expected_fragment in test_case.expected_promote_fragments:
        assert expected_fragment in promote_output


@pytest.mark.parametrize(
    "test_case",
    [
        PythonNodesPlaygroundLifecycleTestCase(
            description="python nodes playground runs plan build and check lifecycle",
            project_name="python_nodes_demo",
            expected_plan_fragments=(
                "raw_orders",
                "fact_orders",
                "Python read-side",
            ),
            expected_build_fragments=(
                "prepare_raw_orders",
                "raw_orders",
                "fact_orders",
                "orders_export",
                "Completed successfully.",
            ),
            expected_check_fragments=(
                "check_orders_export",
                "PASS",
            ),
        )
    ],
    ids=["python nodes playground runs plan build and check lifecycle"],
)
def test_given_python_nodes_playground_when_running_lifecycle_then_it_succeeds(
    test_case: PythonNodesPlaygroundLifecycleTestCase,
    tmp_path: Path,
) -> None:
    assert run_playground(tmp_path, test_case.project_name, template="python_nodes") == 0
    project_dir: Path = tmp_path / test_case.project_name

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "plan",
            "--select",
            "+fact_orders",
            "--select",
            "+orders_export",
        ),
        project_dir=project_dir,
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "build",
            "--select",
            "+fact_orders",
            "--select",
            "+orders_export",
        ),
        project_dir=project_dir,
    )
    check_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "check", "--select", "check_orders_export"),
        project_dir=project_dir,
    )

    plan_output: str = plan_result.stdout + plan_result.stderr
    assert plan_result.returncode == 0
    for expected_fragment in test_case.expected_plan_fragments:
        assert expected_fragment in plan_output

    build_output: str = build_result.stdout + build_result.stderr
    assert build_result.returncode == 0
    for expected_fragment in test_case.expected_build_fragments:
        assert expected_fragment in build_output

    check_output: str = check_result.stdout + check_result.stderr
    assert check_result.returncode == 0
    for expected_fragment in test_case.expected_check_fragments:
        assert expected_fragment in check_output


@pytest.mark.dbt
@pytest.mark.parametrize(
    "test_case",
    [
        DbtChangeAwarePlaygroundLifecycleTestCase(
            description="dbt playground second build prunes unchanged models (change-aware)",
            project_name="dbt_change_aware_playground",
            expected_first_build_fragments=(
                "dbt build",
                "model     stg_orders",
                "model     fct_orders",
            ),
            expected_second_build_fragments=(
                "all planned dbt models are current",
                "no change",
                "Skipping dbt: no dbt work selected.",
            ),
            expected_second_build_absent_fragments=(
                "OK     reuse",
                "Reuse plan",
                "dbt reuse  pre-phase",
                "dbt fingerprint write failed",
            ),
        )
    ],
    ids=["dbt playground second build prunes unchanged models (change-aware)"],
)
def test_given_dbt_playground_when_building_then_runs_dbt_without_reuse(
    test_case: DbtChangeAwarePlaygroundLifecycleTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    assert run_playground(tmp_path, test_case.project_name, template="dbt") == 0
    workspace: Path = tmp_path / test_case.project_name

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "init", "--project-dir", "dbt_project", "--profiles-dir", "profiles"),
        project_dir=workspace,
    )
    assert init_result.returncode == 0, init_result.stdout + init_result.stderr

    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"
    first_build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build"),
        project_dir=sqlbuild_project_dir,
    )
    assert first_build.returncode == 0, first_build.stdout + first_build.stderr
    first_output: str = first_build.stdout + first_build.stderr
    fragment: str
    for fragment in test_case.expected_first_build_fragments:
        assert fragment in first_output

    second_build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build"),
        project_dir=sqlbuild_project_dir,
    )
    assert second_build.returncode == 0, second_build.stdout + second_build.stderr
    second_output: str = second_build.stdout + second_build.stderr
    for fragment in test_case.expected_second_build_fragments:
        assert fragment in second_output
    for fragment in test_case.expected_second_build_absent_fragments:
        assert fragment not in second_output
