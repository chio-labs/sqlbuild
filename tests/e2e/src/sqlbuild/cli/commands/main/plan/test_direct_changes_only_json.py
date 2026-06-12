"""Direct changes-only JSON output E2E tests."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan._test_types import (
    DirectChangesOnlyJsonE2ETestCase,
    DirectPlanIdentityJsonE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import (
    build_direct_changes_only_project_toml,
    direct_changes_only_stg_orders_sql,
    plan_changes_only_json,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DirectChangesOnlyJsonE2ETestCase(
            description="reports semantic staleness with identity diagnostics",
            expected_reasons_by_name={
                "stg_orders": "query_changed",
                "fact_orders": "upstream_changed",
            },
            expected_identity_status_by_name={
                "stg_orders": "stale",
                "fact_orders": "stale",
            },
        )
    ],
    ids=["reports semantic staleness with identity diagnostics"],
)
def test_given_upstream_change_when_planning_json_then_reports_semantic_staleness(
    test_case: DirectChangesOnlyJsonE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="direct_changes_only_json_staleness",
        repo_files={
            "sqlbuild_project.toml": build_direct_changes_only_project_toml(
                project_name="direct_changes_only_json_staleness"
            ),
            "models/stg_orders.sql": direct_changes_only_stg_orders_sql(amount_cents=100),
            "models/fact_orders.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT order_id, amount_cents FROM __ref("stg_orders")\n'
            ),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    (project_dir / "models" / "stg_orders.sql").write_text(
        direct_changes_only_stg_orders_sql(amount_cents=125),
        encoding="utf-8",
    )

    payload: dict[str, object] = plan_changes_only_json(project_dir=project_dir)

    models: list[dict[str, object]] = cast(list[dict[str, object]], payload["models"])
    assert {str(model["name"]): str(model["reason"]) for model in models} == (
        test_case.expected_reasons_by_name
    )
    assert {str(model["name"]): str(model["identity_status"]) for model in models} == (
        test_case.expected_identity_status_by_name
    )
    model: dict[str, object]
    for model in models:
        assert isinstance(model["expected_version_hash"], str)
        assert isinstance(model["built_version_hash"], str)
        assert model["built_version_present"] is True


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanIdentityJsonE2ETestCase(
            description="first run reports missing built identity",
            project_name="direct_json_identity_missing",
            expected_identity_status="missing",
            expected_built_version_present=False,
        )
    ],
    ids=["first run reports missing built identity"],
)
def test_given_first_run_when_planning_json_then_reports_missing_identity(
    test_case: DirectPlanIdentityJsonE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": build_direct_changes_only_project_toml(
                project_name=test_case.project_name
            ),
            "models/orders.sql": direct_changes_only_stg_orders_sql(amount_cents=100),
        },
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--json", "--force"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    payload: dict[str, object] = json.loads(plan_result.stdout)
    models: list[dict[str, object]] = cast(list[dict[str, object]], payload["models"])
    assert len(models) == 1
    model: dict[str, object] = models[0]
    assert isinstance(model["expected_version_hash"], str)
    assert model["built_version_hash"] is None
    assert model["built_version_present"] is test_case.expected_built_version_present
    assert model["identity_status"] == test_case.expected_identity_status


@pytest.mark.parametrize(
    "test_case",
    [
        DirectPlanIdentityJsonE2ETestCase(
            description="current build reports current identity",
            project_name="direct_json_identity_current",
            expected_identity_status="current",
            expected_built_version_present=True,
        )
    ],
    ids=["current build reports current identity"],
)
def test_given_current_build_when_planning_json_then_reports_current_identity(
    test_case: DirectPlanIdentityJsonE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        repo_files={
            "sqlbuild_project.toml": build_direct_changes_only_project_toml(
                project_name=test_case.project_name
            ),
            "models/orders.sql": direct_changes_only_stg_orders_sql(amount_cents=100),
        },
    )
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stdout + build_result.stderr

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "plan", "--json", "--force"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    payload: dict[str, object] = json.loads(plan_result.stdout)
    models: list[dict[str, object]] = cast(list[dict[str, object]], payload["models"])
    assert len(models) == 1
    model: dict[str, object] = models[0]
    assert isinstance(model["expected_version_hash"], str)
    assert model["built_version_hash"] == model["expected_version_hash"]
    assert model["built_version_present"] is test_case.expected_built_version_present
    assert model["identity_status"] == test_case.expected_identity_status
