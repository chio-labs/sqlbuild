"""Direct changes-only function identity E2E tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    DirectFunctionIdentityE2ETestCase,
    DirectFunctionSelectorE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    direct_model_version_hashes,
    prepare_direct_function_identity_project,
    rewrite_direct_is_large_order_function,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        DirectFunctionIdentityE2ETestCase(
            description="function change updates dependent model version hash after build",
            expected_initial_count=1,
            expected_changed_count=1,
            expected_model_name="orders",
        )
    ],
    ids=["function change updates dependent model version hash after build"],
)
def test_given_function_change_when_building_dependent_then_model_version_hash_changes(
    test_case: DirectFunctionIdentityE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_function_identity_project(
        tmp_path=tmp_path,
        project_name="direct_function_identity_version_hash",
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    initial_build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_build.returncode == 0, initial_build.stdout + initial_build.stderr
    initial_hashes: list[tuple[object, ...]] = direct_model_version_hashes(
        db_path=db_path, model_name=test_case.expected_model_name
    )
    assert len(initial_hashes) == test_case.expected_initial_count

    rewrite_direct_is_large_order_function(project_dir=project_dir, operator=">=")
    changed_build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only", "--select", "+orders"),
        project_dir=project_dir,
    )

    assert changed_build.returncode == 0, changed_build.stdout + changed_build.stderr
    changed_hashes: list[tuple[object, ...]] = direct_model_version_hashes(
        db_path=db_path, model_name=test_case.expected_model_name
    )
    assert len(changed_hashes) == test_case.expected_changed_count + 1
    assert changed_hashes[0][0] != changed_hashes[-1][0]


TEST_CASES: list[DirectFunctionSelectorE2ETestCase] = [
    DirectFunctionSelectorE2ETestCase(
        description="function selector stays on changed function only",
        selector="is_large_order",
        expected_plan_fragment="Plan ready (",
        expected_fragments=("Changed functions (1)", "is_large_order"),
        unexpected_fragments=("Upstream changed",),
        expected_remaining_stale_names=("orders",),
    ),
    DirectFunctionSelectorE2ETestCase(
        description="dependent upstream expansion includes changed function and model",
        selector="+orders",
        expected_plan_fragment="Plan ready (",
        expected_fragments=("Changed functions (1)", "is_large_order", "orders"),
        unexpected_fragments=("Plan ready (0 selected)",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_function_change_when_planning_with_selector_then_respects_function_scope(
    test_case: DirectFunctionSelectorE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_function_identity_project(
        tmp_path=tmp_path,
        project_name="direct_function_identity_selector",
    )
    initial_build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_build.returncode == 0, initial_build.stdout + initial_build.stderr
    rewrite_direct_is_large_order_function(project_dir=project_dir, operator=">=")

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--changes-only", "--select", test_case.selector),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    assert test_case.expected_plan_fragment in plan_result.stdout
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in plan_result.stdout, plan_result.stdout
    for fragment in test_case.unexpected_fragments:
        assert fragment not in plan_result.stdout, plan_result.stdout
    assert ("Remaining stale" in plan_result.stdout) == bool(
        test_case.expected_remaining_stale_names
    ), plan_result.stdout
    for model_name in test_case.expected_remaining_stale_names:
        assert model_name in plan_result.stdout, plan_result.stdout
