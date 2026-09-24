"""E2E parity between Dagster asset selection and SQLBuild planner selection."""

import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import dagster as dg
import pytest

from sqlbuild.integrations.dagster import build_sqlbuild_asset_selection, sqlbuild_assets
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_waffle_shop, run_sqb
from tests.e2e.src.sqlbuild.integrations.dagster._test_types import (
    DagsterSelectorParityE2ETestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        DagsterSelectorParityE2ETestCase(
            description="both-direction expansion matches the planner",
            select="+daily_revenue+",
            expected_model_names=("daily_revenue", "stg_orders", "stg_payments"),
        ),
        DagsterSelectorParityE2ETestCase(
            description="path selector keeps every path like the planner",
            select="+fact_orders~hourly_activity_with_daily_context",
            expected_model_names=(
                "daily_activity_rollup",
                "fact_orders",
                "hourly_activity_with_daily_context",
                "hourly_order_activity",
                "stg_orders",
                "stg_payments",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_waffle_shop_selector_when_resolving_in_dagster_then_models_match_planner(
    test_case: DagsterSelectorParityE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    dag_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dag", "--json"), project_dir=project_dir
    )
    assert dag_result.returncode == 0, dag_result.stdout + dag_result.stderr
    dag: Mapping[str, Any] = json.loads(dag_result.stdout)
    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("plan", "--select", test_case.select, "--json"), project_dir=project_dir
    )
    assert plan_result.returncode == 0, plan_result.stdout + plan_result.stderr
    planned_model_names: tuple[str, ...] = tuple(
        sorted(str(entry["name"]) for entry in json.loads(plan_result.stdout)["models"])
    )

    @sqlbuild_assets(dag=dag)
    def waffle_shop_assets() -> dg.MaterializeResult:
        return dg.MaterializeResult()

    selection: Any = build_sqlbuild_asset_selection(
        sqlbuild_assets=[waffle_shop_assets],
        dag=dag,
        sqlbuild_select=test_case.select,
    )
    kind_and_name_by_asset_key: dict[tuple[str, ...], tuple[str, str]] = {
        tuple(node["asset_key"]): (str(node["kind"]), str(node["name"])) for node in dag["nodes"]
    }
    selected_kind_and_names: set[tuple[str, str]] = {
        kind_and_name_by_asset_key[tuple(key.path)]
        for key in selection.resolve([waffle_shop_assets])
    }
    model_kind_and_names: set[tuple[str, str]] = {
        ("model", name) for _, name in kind_and_name_by_asset_key.values()
    }
    dagster_model_names: tuple[str, ...] = tuple(
        sorted(name for _, name in selected_kind_and_names & model_kind_and_names)
    )

    assert planned_model_names == test_case.expected_model_names
    assert dagster_model_names == test_case.expected_model_names
