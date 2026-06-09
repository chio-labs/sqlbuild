"""E2E tests for direct changes-only state and downstream data correctness."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    DirectChangesOnlyStateBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    prepare_direct_changes_only_two_model_project,
    write_direct_changes_only_stg_orders,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyStateBuildE2ETestCase(
            description="changes-only rebuilds downstream data",
            project_name="direct_changes_only_build_updates_downstream",
            initial_amount_cents=100,
            changed_amount_cents=125,
            expected_initial_amount_dollars=1.0,
            expected_changed_amount_dollars=1.25,
        )
    ],
    ids=["changes-only rebuilds downstream data"],
)
def test_given_upstream_query_change_when_building_changes_only_then_rebuilds_downstream_data(
    test_case: DirectChangesOnlyStateBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_changes_only_two_model_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        amount_cents=test_case.initial_amount_cents,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

    write_direct_changes_only_stg_orders(
        project_dir=project_dir, amount_cents=test_case.changed_amount_cents
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    assert "Plan ready (2 selected)" in build_result.stdout
    assert "stg_orders" in build_result.stdout
    assert "fact_orders" in build_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT amount_cents, amount_dollars FROM fact_orders ORDER BY order_id",
    ) == [(test_case.changed_amount_cents, test_case.expected_changed_amount_dollars)]


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyStateBuildE2ETestCase(
            description="scoped build leaves downstream stale then later catches up",
            project_name="direct_changes_only_build_scoped_then_later",
            initial_amount_cents=100,
            changed_amount_cents=125,
            expected_initial_amount_dollars=1.0,
            expected_changed_amount_dollars=1.25,
        )
    ],
    ids=["scoped build leaves downstream stale then later catches up"],
)
def test_given_scoped_upstream_changes_only_build_when_building_later_then_downstream_catches_up(
    test_case: DirectChangesOnlyStateBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_direct_changes_only_two_model_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        amount_cents=test_case.initial_amount_cents,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

    write_direct_changes_only_stg_orders(
        project_dir=project_dir, amount_cents=test_case.changed_amount_cents
    )
    scoped_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only", "--select", "stg_orders"),
        project_dir=project_dir,
    )

    assert scoped_result.returncode == 0, scoped_result.stdout + scoped_result.stderr
    assert "Plan ready (1 selected)" in scoped_result.stdout
    assert "stg_orders" in scoped_result.stdout
    assert "Remaining stale" in scoped_result.stdout
    assert "model set: fact_orders" in scoped_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT amount_cents, amount_dollars FROM fact_orders ORDER BY order_id",
    ) == [(test_case.initial_amount_cents, test_case.expected_initial_amount_dollars)]

    later_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--changes-only"),
        project_dir=project_dir,
    )

    assert later_result.returncode == 0, later_result.stdout + later_result.stderr
    assert "Plan ready (1 selected)" in later_result.stdout
    assert "fact_orders" in later_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT amount_cents, amount_dollars FROM fact_orders ORDER BY order_id",
    ) == [(test_case.changed_amount_cents, test_case.expected_changed_amount_dollars)]
