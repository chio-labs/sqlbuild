from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtPhase11ExecutionTestCase,
    DbtPhase11ModelFailureTestCase,
    DbtPhase11NonModelWorkTestCase,
    DbtPhase11PlanOutputTestCase,
    DbtPhase11ReplayFullTestCase,
    DbtPhase11SqlbuildNativePlanTestCase,
    DbtPhase11SourceBlockingTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    add_dbt_phase11_sqlbuild_function_branch,
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
                "Skipping SQLBuild: selected models are already current.",
                "skipped: all planned dbt models are current",
                "Skipped current models",
            ),
            expected_current_absent_stdout_fragments=("Plan ready (0 selected)",),
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
            "WHERE node_type = 'dbt' AND node_name LIKE 'model.%' ORDER BY node_name"
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
    for expected_fragment in test_case.expected_current_absent_stdout_fragments:
        assert expected_fragment not in current_result.stdout
    assert current_result.stdout.count("Plan ready") == 1

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
        DbtPhase11ModelFailureTestCase(
            description="failed dbt model blocks downstream SQLBuild while unrelated branch runs",
            expected_returncode=1,
            expected_stdout_fragments=(
                "FAIL",
                "SQLBuild execution",
                "customer_summary",
                "Completed successfully.",
            ),
            expected_absent_relations=("downstream_orders",),
            expected_customer_rows=((10, "Ada"),),
        )
    ],
    ids=["failed dbt model blocks downstream SQLBuild while unrelated branch runs"],
)
def test_given_dbt_model_failure_when_building_then_blocks_affected_sqlbuild_branch(
    test_case: DbtPhase11ModelFailureTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    write_dbt_phase11_fact_orders_model(
        project_dir=project_dir,
        amount_expression="missing_amount",
    )

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
        DbtPhase11NonModelWorkTestCase(
            description="current dbt producers prune selected seed and test work",
            command=(
                "dbt",
                "build",
                "--select",
                "downstream_orders",
                "country_codes",
                "not_null_fact_orders_order_id",
            ),
            expected_stdout_fragments=(
                "Seeds pruned (1)",
                "country_codes",
                "Tests pruned (1)",
                "not_null_fact_orders_order_id",
                "use sqb dbt test to run dbt validation",
                "Skipping dbt: no dbt work selected.",
            ),
            unexpected_stdout_fragments=("dbt execution", "seed      country_codes"),
        )
    ],
    ids=["current dbt producers prune selected seed and test work"],
)
def test_given_current_dbt_models_when_seed_and_test_selected_then_prunes_non_model_work(
    test_case: DbtPhase11NonModelWorkTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    setup_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "downstream_orders", "customer_summary"),
        project_dir=project_dir,
    )
    assert setup_result.returncode == 0, setup_result.stderr or setup_result.stdout

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr or result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_stdout_fragments:
        assert unexpected_fragment not in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11NonModelWorkTestCase(
            description="changed dbt model preserves selected seed and test work",
            command=(
                "dbt",
                "build",
                "--select",
                "downstream_orders",
                "country_codes",
                "not_null_fact_orders_order_id",
            ),
            expected_stdout_fragments=(
                "Non-model dbt work",
                "Seeds (1, always run)",
                "country_codes",
                "Tests (1)",
                "not_null_fact_orders_order_id",
                "dbt execution",
                "seed",
                "test",
            ),
            unexpected_stdout_fragments=("Tests pruned", "Seeds pruned"),
        )
    ],
    ids=["changed dbt model preserves selected seed and test work"],
)
def test_given_changed_dbt_model_when_seed_and_test_selected_then_runs_non_model_work(
    test_case: DbtPhase11NonModelWorkTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    setup_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "downstream_orders", "customer_summary"),
        project_dir=project_dir,
    )
    assert setup_result.returncode == 0, setup_result.stderr or setup_result.stdout
    write_dbt_phase11_fact_orders_model(
        project_dir=project_dir,
        amount_expression="amount + 11",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr or result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_stdout_fragments:
        assert unexpected_fragment not in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11SqlbuildNativePlanTestCase(
            description="dbt interop preserves native SQLBuild function plan details",
            expected_stdout_fragments=(
                "Changed functions (1)",
                "is_large_amount",
                "First run (1)",
                "amount_quality",
                "SQLBuild execution",
            ),
            expected_rows=((1, True),),
        )
    ],
    ids=["dbt interop preserves native SQLBuild function plan details"],
)
def test_given_current_dbt_and_new_sqlbuild_function_when_building_then_shows_native_plan_detail(
    test_case: DbtPhase11SqlbuildNativePlanTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    setup_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "downstream_orders", "customer_summary"),
        project_dir=project_dir,
    )
    assert setup_result.returncode == 0, setup_result.stderr or setup_result.stdout
    add_dbt_phase11_sqlbuild_function_branch(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "amount_quality", "customer_summary"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    assert query_duckdb(
        db_path=project_dir / "dbt_phase11.duckdb",
        sql="SELECT order_id, is_large_amount FROM main.amount_quality ORDER BY order_id",
    ) == list(test_case.expected_rows)


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
