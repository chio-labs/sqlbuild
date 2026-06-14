from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtPhase11ExecutionTestCase,
    DbtPhase11PlanOutputTestCase,
    DbtPhase11ReplayFullTestCase,
    DbtPhase11SourceBlockingTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    load_json_stdout,
    prepare_dbt_phase11_project,
    seed_dbt_phase11_sources,
    skip_unless_dbt_is_runnable,
    write_dbt_phase11_fact_orders_model,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    query_duckdb,
    run_sqb,
    table_exists,
)

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11ExecutionTestCase(
            description=(
                "current dbt models are pruned and changed dbt models rebuild SQLBuild downstream"
            ),
            expected_current_stdout_fragments=(
                "Model plan",
                "Current (2)",
                "Skipping dbt: no dbt work selected.",
                "skipped: all planned dbt models are current",
                "Skipped current models",
            ),
            expected_changed_rows=((1, 105),),
            expected_fingerprint_unique_ids=(
                "model.analytics.fact_orders",
                "model.analytics.stg_orders",
            ),
        )
    ],
    ids=["current dbt models are pruned and changed dbt models rebuild SQLBuild downstream"],
)
def test_given_built_dbt_models_when_rerunning_and_changing_model_then_prunes_and_cascades(
    test_case: DbtPhase11ExecutionTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_phase11.duckdb"

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "downstream_orders"),
        project_dir=project_dir,
    )
    assert first_result.returncode == 0, first_result.stderr or first_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_name FROM main._sqlbuild_fingerprints "
            "WHERE node_type = 'dbt' ORDER BY node_name"
        ),
    ) == [(unique_id,) for unique_id in test_case.expected_fingerprint_unique_ids]

    current_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "downstream_orders"),
        project_dir=project_dir,
    )
    assert current_result.returncode == 0, current_result.stderr or current_result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_current_stdout_fragments:
        assert expected_fragment in current_result.stdout

    write_dbt_phase11_fact_orders_model(
        project_dir=project_dir,
        amount_expression="amount + 5",
    )
    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "downstream_orders"),
        project_dir=project_dir,
    )
    assert changed_result.returncode == 0, changed_result.stderr or changed_result.stdout
    assert "model.analytics.fact_orders" in changed_result.stdout
    assert "SQLBuild execution" in changed_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, downstream_amount FROM main.downstream_orders ORDER BY order_id",
    ) == list(test_case.expected_changed_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11SourceBlockingTestCase(
            description="stale dbt source blocks affected branch while unrelated branch runs",
            expected_returncode=1,
            expected_stdout_fragments=(
                "Model plan",
                "Blocked (2)",
                "customer_summary",
                "Completed successfully.",
            ),
            expected_absent_relations=("downstream_orders",),
            expected_customer_rows=((10, "Ada"),),
        )
    ],
    ids=["stale dbt source blocks affected branch while unrelated branch runs"],
)
def test_given_dbt_source_freshness_error_when_building_then_blocks_affected_branch(
    test_case: DbtPhase11SourceBlockingTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    seed_dbt_phase11_sources(project_dir=project_dir, stale_orders=True)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "downstream_orders", "customer_summary"),
        project_dir=project_dir,
    )

    db_path: Path = project_dir / "dbt_phase11.duckdb"
    assert result.returncode == test_case.expected_returncode, result.stderr or result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    relation_name: str
    for relation_name in test_case.expected_absent_relations:
        assert not table_exists(db_path=db_path, table_name=relation_name), relation_name
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT customer_id, customer_name FROM main.customer_summary ORDER BY customer_id",
    ) == list(test_case.expected_customer_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11PlanOutputTestCase(
            description="plan JSON and human output include dbt model plan state",
            expected_current_unique_ids=(
                "model.analytics.fact_orders",
                "model.analytics.stg_orders",
            ),
            expected_stdout_fragments=("Model plan", "Current (2)"),
        )
    ],
    ids=["plan JSON and human output include dbt model plan state"],
)
def test_given_current_dbt_models_when_planning_then_outputs_model_plan_state(
    test_case: DbtPhase11PlanOutputTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "downstream_orders"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stderr or build_result.stdout

    json_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--json", "--select", "downstream_orders"),
        project_dir=project_dir,
    )
    assert json_result.returncode == 0, json_result.stderr or json_result.stdout
    payload: dict[str, object] = load_json_stdout(json_result.stdout)
    dbt_payload: Mapping[str, object] = cast(Mapping[str, object], payload["dbt"])
    model_plan: Mapping[str, object] = cast(Mapping[str, object], dbt_payload["model_plan"])
    assert model_plan["current_unique_ids"] == list(test_case.expected_current_unique_ids)

    human_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--select", "downstream_orders"),
        project_dir=project_dir,
    )
    assert human_result.returncode == 0, human_result.stderr or human_result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in human_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11ReplayFullTestCase(
            description="dbt replay_on_change full adds full refresh for changed dbt work",
            expected_stdout_fragments=("--full-refresh", "model.analytics.fact_orders"),
            expected_rows=((1, 107),),
        )
    ],
    ids=["dbt replay_on_change full adds full refresh for changed dbt work"],
)
def test_given_dbt_replay_full_when_model_changes_then_dbt_execution_uses_full_refresh(
    test_case: DbtPhase11ReplayFullTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(
        tmp_path=tmp_path,
        replay_on_change="full",
    )
    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "downstream_orders"),
        project_dir=project_dir,
    )
    assert first_result.returncode == 0, first_result.stderr or first_result.stdout
    write_dbt_phase11_fact_orders_model(
        project_dir=project_dir,
        amount_expression="amount + 7",
    )

    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "downstream_orders"),
        project_dir=project_dir,
    )

    assert changed_result.returncode == 0, changed_result.stderr or changed_result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in changed_result.stdout
    assert query_duckdb(
        db_path=project_dir / "dbt_phase11.duckdb",
        sql="SELECT order_id, downstream_amount FROM main.downstream_orders ORDER BY order_id",
    ) == list(test_case.expected_rows)
