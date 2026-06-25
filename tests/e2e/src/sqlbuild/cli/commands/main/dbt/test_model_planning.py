from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtFullRefreshScopeTestCase,
    DbtPhase11DbtOnlySourceFreshnessTestCase,
    DbtPhase11ExecutionTestCase,
    DbtPhase11FreshnessEdgeCaseTestCase,
    DbtPhase11ModelFailureTestCase,
    DbtPhase11MultiSourceFreshnessTestCase,
    DbtPhase11NonModelWorkTestCase,
    DbtPhase11PlanOutputTestCase,
    DbtPhase11QueryFilterFreshnessTestCase,
    DbtPhase11ReplayFullTestCase,
    DbtPhase11SourceBlockingTestCase,
    DbtPhase11SourceFreshnessChangeTestCase,
    DbtPhase11SourceObservationErrorTestCase,
    DbtPhase11SqlbuildNativePlanTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    add_dbt_phase11_payments_branch,
    add_dbt_phase11_query_filter_branch,
    add_dbt_phase11_sqlbuild_function_branch,
    load_json_stdout,
    prepare_dbt_phase11_project,
    query_dbt_phase11_schema_source_freshness_rows,
    query_dbt_phase11_source_freshness_rows,
    seed_dbt_phase11_sources,
    set_dbt_phase11_sqlbuild_target_schema,
    skip_unless_dbt_is_runnable,
    write_dbt_phase11_fact_orders_model,
    write_dbt_phase11_invalid_downstream_model,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    execute_duckdb,
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
        command=("dbt", "build", "--select", "+downstream_orders"),
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
        command=("dbt", "build", "--select", "+downstream_orders"),
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
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert changed_result.returncode == 0, changed_result.stderr or changed_result.stdout
    assert "dbt execution" in changed_result.stdout
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
                "customer_summary",
                "Completed successfully.",
            ),
            expected_absent_relations=("downstream_orders",),
            expected_customer_rows=((10, "Ada"),),
            expected_source_freshness_rows=(),
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
        command=("dbt", "build", "--select", "+downstream_orders", "+customer_summary"),
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
    assert query_dbt_phase11_source_freshness_rows(project_dir=project_dir) == list(
        test_case.expected_source_freshness_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11SourceFreshnessChangeTestCase(
            description="changed dbt source freshness reruns dbt and SQLBuild downstream",
            expected_current_stdout_fragments=(
                "Model plan",
                "Current (2)",
                "Skipping dbt: no dbt work selected.",
                "Skipping SQLBuild: selected models are already current.",
            ),
            expected_plan_run_unique_ids=(
                "model.analytics.fact_orders",
                "model.analytics.stg_orders",
            ),
            expected_plan_reasons=(
                "source_freshness_changed",
                "source_freshness_changed",
            ),
            expected_plan_stale_sqlbuild_model_names=("downstream_orders",),
            expected_plan_current_unique_ids=(
                "model.analytics.dim_customers",
                "model.analytics.stg_customers",
            ),
            expected_source_freshness_rows=(
                ("source.analytics.raw.orders", "2999-01-01T00:00:00"),
            ),
            expected_changed_stdout_fragments=(
                "dbt execution",
                "SQLBuild execution",
            ),
            expected_rows=((1, 125),),
        )
    ],
    ids=["changed dbt source freshness reruns dbt and SQLBuild downstream"],
)
def test_given_dbt_source_freshness_changes_when_building_then_reruns_downstream_work(
    test_case: DbtPhase11SourceFreshnessChangeTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_phase11.duckdb"
    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders", "+customer_summary"),
        project_dir=project_dir,
    )
    assert first_result.returncode == 0, first_result.stderr or first_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT source_name, data_version FROM main._sqlbuild_source_freshness "
            "WHERE source_name = 'source.analytics.raw.orders' "
            "ORDER BY source_name, data_version"
        ),
    ) == list(test_case.expected_source_freshness_rows)

    current_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert current_result.returncode == 0, current_result.stderr or current_result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_current_stdout_fragments:
        assert expected_fragment in current_result.stdout

    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_orders AS "
            "SELECT 1 AS order_id, 10 AS customer_id, 125 AS amount, "
            "TIMESTAMP '2999-01-02 00:00:00' AS loaded_at"
        ),
    )
    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "dbt",
            "plan",
            "--json",
            "--select",
            "+downstream_orders",
            "+customer_summary",
        ),
        project_dir=project_dir,
    )
    assert plan_result.returncode == 0, plan_result.stderr or plan_result.stdout
    plan_payload: dict[str, object] = load_json_stdout(plan_result.stdout)
    dbt_payload: Mapping[str, object] = cast(Mapping[str, object], plan_payload["dbt"])
    model_plan: Mapping[str, object] = cast(Mapping[str, object], dbt_payload["model_plan"])
    assert model_plan["run_unique_ids"] == list(test_case.expected_plan_run_unique_ids)
    assert model_plan["current_unique_ids"] == list(test_case.expected_plan_current_unique_ids)
    assert model_plan["stale_sqlbuild_model_names"] == list(
        test_case.expected_plan_stale_sqlbuild_model_names
    )
    entries: list[object] = cast(list[object], model_plan["entries"])
    run_entries: tuple[Mapping[str, object], ...] = tuple(
        cast(Mapping[str, object], entry)
        for entry in entries
        if cast(Mapping[str, object], entry)["action"] == "run"
    )
    assert tuple(entry["reason"] for entry in run_entries) == test_case.expected_plan_reasons

    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )

    assert changed_result.returncode == 0, changed_result.stderr or changed_result.stdout
    for expected_fragment in test_case.expected_changed_stdout_fragments:
        assert expected_fragment in changed_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, downstream_amount FROM main.downstream_orders ORDER BY order_id",
    ) == list(test_case.expected_rows)

    final_current_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert final_current_result.returncode == 0, (
        final_current_result.stderr or final_current_result.stdout
    )
    for expected_fragment in test_case.expected_current_stdout_fragments:
        assert expected_fragment in final_current_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11DbtOnlySourceFreshnessTestCase(
            description="dbt-only selector uses source freshness state without SQLBuild staleness",
            expected_current_stdout_fragments=(
                "Model plan",
                "Current (1)",
                "Skipping dbt: no dbt work selected.",
            ),
            expected_plan_run_unique_ids=("model.analytics.stg_orders",),
            expected_plan_reasons=("source_freshness_changed",),
            expected_plan_stale_sqlbuild_model_names=("downstream_orders",),
            expected_rows=((1, 140),),
        )
    ],
    ids=["dbt-only selector uses source freshness state without SQLBuild staleness"],
)
def test_given_dbt_only_selector_when_source_freshness_changes_then_reruns_dbt_model_only(
    test_case: DbtPhase11DbtOnlySourceFreshnessTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_phase11.duckdb"
    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "stg_orders"),
        project_dir=project_dir,
    )
    assert first_result.returncode == 0, first_result.stderr or first_result.stdout

    current_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "stg_orders"),
        project_dir=project_dir,
    )
    assert current_result.returncode == 0, current_result.stderr or current_result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_current_stdout_fragments:
        assert expected_fragment in current_result.stdout

    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_orders AS "
            "SELECT 1 AS order_id, 10 AS customer_id, 140 AS amount, "
            "TIMESTAMP '2999-01-03 00:00:00' AS loaded_at"
        ),
    )
    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--json", "--select", "stg_orders"),
        project_dir=project_dir,
    )
    assert plan_result.returncode == 0, plan_result.stderr or plan_result.stdout
    plan_payload: dict[str, object] = load_json_stdout(plan_result.stdout)
    dbt_payload: Mapping[str, object] = cast(Mapping[str, object], plan_payload["dbt"])
    model_plan: Mapping[str, object] = cast(Mapping[str, object], dbt_payload["model_plan"])
    assert model_plan["run_unique_ids"] == list(test_case.expected_plan_run_unique_ids)
    assert model_plan["stale_sqlbuild_model_names"] == list(
        test_case.expected_plan_stale_sqlbuild_model_names
    )
    entries: list[object] = cast(list[object], model_plan["entries"])
    run_entries: tuple[Mapping[str, object], ...] = tuple(
        cast(Mapping[str, object], entry)
        for entry in entries
        if cast(Mapping[str, object], entry)["action"] == "run"
    )
    assert tuple(entry["reason"] for entry in run_entries) == test_case.expected_plan_reasons

    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "stg_orders"),
        project_dir=project_dir,
    )

    assert changed_result.returncode == 0, changed_result.stderr or changed_result.stdout
    assert "dbt execution" in changed_result.stdout
    assert "SQLBuild execution" not in changed_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, amount FROM main.stg_orders ORDER BY order_id",
    ) == list(test_case.expected_rows)

    final_current_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "stg_orders"),
        project_dir=project_dir,
    )
    assert final_current_result.returncode == 0, (
        final_current_result.stderr or final_current_result.stdout
    )
    for expected_fragment in test_case.expected_current_stdout_fragments:
        assert expected_fragment in final_current_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11SourceObservationErrorTestCase(
            description="empty dbt source is unknown and does not persist freshness state",
            expected_returncode=0,
            expected_stdout_fragments=("Skipping dbt: no dbt work selected.",),
            expected_absent_relations=(),
            expected_source_freshness_rows=(),
        )
    ],
    ids=["empty dbt source is unknown and does not persist freshness state"],
)
def test_given_empty_dbt_source_when_rerunning_then_models_are_current_without_freshness_state(
    test_case: DbtPhase11SourceObservationErrorTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_phase11.duckdb"
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_orders "
            "(order_id INTEGER, customer_id INTEGER, amount INTEGER, loaded_at TIMESTAMP)"
        ),
    )

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert first_result.returncode == test_case.expected_returncode, (
        first_result.stderr or first_result.stdout
    )
    assert (
        query_duckdb(
            db_path=db_path,
            sql="SELECT order_id, downstream_amount FROM main.downstream_orders ORDER BY order_id",
        )
        == []
    )
    assert query_dbt_phase11_source_freshness_rows(project_dir=project_dir) == list(
        test_case.expected_source_freshness_rows
    )

    current_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert current_result.returncode == test_case.expected_returncode, (
        current_result.stderr or current_result.stdout
    )
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in current_result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11MultiSourceFreshnessTestCase(
            description="one changed source reruns model that also depends on unchanged source",
            expected_run_unique_ids=("model.analytics.order_payments",),
            expected_run_reasons=("source_freshness_changed",),
            expected_stale_sqlbuild_model_names=("payment_summary",),
            expected_rows=((1, 250),),
        )
    ],
    ids=["one changed source reruns model that also depends on unchanged source"],
)
def test_given_multi_source_dbt_model_when_one_source_changes_then_model_reruns(
    test_case: DbtPhase11MultiSourceFreshnessTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_phase11.duckdb"
    add_dbt_phase11_payments_branch(project_dir=project_dir)
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_payments AS "
            "SELECT 1 AS order_id, 200 AS payment_amount, "
            "TIMESTAMP '2999-01-01 00:00:00' AS loaded_at"
        ),
    )
    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+payment_summary"),
        project_dir=project_dir,
    )
    assert first_result.returncode == 0, first_result.stderr or first_result.stdout

    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_payments AS "
            "SELECT 1 AS order_id, 250 AS payment_amount, "
            "TIMESTAMP '2999-01-02 00:00:00' AS loaded_at"
        ),
    )
    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--json", "--select", "+payment_summary"),
        project_dir=project_dir,
    )
    assert plan_result.returncode == 0, plan_result.stderr or plan_result.stdout
    plan_payload: dict[str, object] = load_json_stdout(plan_result.stdout)
    dbt_payload: Mapping[str, object] = cast(Mapping[str, object], plan_payload["dbt"])
    model_plan: Mapping[str, object] = cast(Mapping[str, object], dbt_payload["model_plan"])
    assert model_plan["run_unique_ids"] == list(test_case.expected_run_unique_ids)
    assert model_plan["stale_sqlbuild_model_names"] == list(
        test_case.expected_stale_sqlbuild_model_names
    )
    entries: list[object] = cast(list[object], model_plan["entries"])
    run_entries: tuple[Mapping[str, object], ...] = tuple(
        cast(Mapping[str, object], entry)
        for entry in entries
        if cast(Mapping[str, object], entry)["action"] == "run"
    )
    assert tuple(entry["reason"] for entry in run_entries) == test_case.expected_run_reasons

    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+payment_summary"),
        project_dir=project_dir,
    )
    assert changed_result.returncode == 0, changed_result.stderr or changed_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, payment_amount FROM main.payment_summary ORDER BY order_id",
    ) == list(test_case.expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11QueryFilterFreshnessTestCase(
            description="loaded_at_query and filtered freshness drive dbt interop state",
            expected_run_unique_ids=("model.analytics.event_rollup",),
            expected_run_reasons=("source_freshness_changed",),
            expected_stale_sqlbuild_model_names=("event_summary",),
            expected_source_freshness_rows=(
                ("source.analytics.raw.filtered_events", "2999-01-01T00:00:00"),
                ("source.analytics.raw.orders", "2999-01-01T00:00:00"),
                ("source.analytics.raw.query_events", "2999-01-01T00:00:00"),
            ),
            expected_rows=((1, 310), (2, 320), (3, 999)),
        )
    ],
    ids=["loaded_at_query and filtered freshness drive dbt interop state"],
)
def test_given_query_and_filtered_dbt_sources_when_source_changes_then_freshness_reruns_model(
    test_case: DbtPhase11QueryFilterFreshnessTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_phase11.duckdb"
    add_dbt_phase11_query_filter_branch(project_dir=project_dir)
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_query_events AS "
            "SELECT 1 AS event_id, 300 AS event_amount, "
            "TIMESTAMP '2999-01-01 00:00:00' AS loaded_at"
        ),
    )
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_filtered_events AS "
            "SELECT 2 AS event_id, 301 AS event_amount, "
            "TIMESTAMP '2999-01-01 00:00:00' AS loaded_at, true AS include_in_freshness "
            "UNION ALL SELECT 3, 999, TIMESTAMP '2999-01-10 00:00:00', false"
        ),
    )
    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+event_summary"),
        project_dir=project_dir,
    )
    assert first_result.returncode == 0, first_result.stderr or first_result.stdout
    assert query_dbt_phase11_source_freshness_rows(project_dir=project_dir) == list(
        test_case.expected_source_freshness_rows
    )

    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_query_events AS "
            "SELECT 1 AS event_id, 310 AS event_amount, "
            "TIMESTAMP '2999-01-02 00:00:00' AS loaded_at"
        ),
    )
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_filtered_events AS "
            "SELECT 2 AS event_id, 320 AS event_amount, "
            "TIMESTAMP '2999-01-01 00:00:00' AS loaded_at, true AS include_in_freshness "
            "UNION ALL SELECT 3, 999, TIMESTAMP '2999-01-20 00:00:00', false"
        ),
    )
    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--json", "--select", "+event_summary"),
        project_dir=project_dir,
    )
    assert plan_result.returncode == 0, plan_result.stderr or plan_result.stdout
    plan_payload: dict[str, object] = load_json_stdout(plan_result.stdout)
    dbt_payload: Mapping[str, object] = cast(Mapping[str, object], plan_payload["dbt"])
    model_plan: Mapping[str, object] = cast(Mapping[str, object], dbt_payload["model_plan"])
    assert model_plan["run_unique_ids"] == list(test_case.expected_run_unique_ids)
    assert model_plan["stale_sqlbuild_model_names"] == list(
        test_case.expected_stale_sqlbuild_model_names
    )
    entries: list[object] = cast(list[object], model_plan["entries"])
    run_entries: tuple[Mapping[str, object], ...] = tuple(
        cast(Mapping[str, object], entry)
        for entry in entries
        if cast(Mapping[str, object], entry)["action"] == "run"
    )
    assert tuple(entry["reason"] for entry in run_entries) == test_case.expected_run_reasons

    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+event_summary"),
        project_dir=project_dir,
    )
    assert changed_result.returncode == 0, changed_result.stderr or changed_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT event_id, event_amount FROM main.event_summary ORDER BY event_id",
    ) == list(test_case.expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11FreshnessEdgeCaseTestCase(
            description="backward dbt source freshness movement reruns downstream work",
            expected_run_unique_ids=(
                "model.analytics.fact_orders",
                "model.analytics.stg_orders",
            ),
            expected_run_reasons=(
                "source_freshness_changed",
                "source_freshness_changed",
            ),
            expected_stale_sqlbuild_model_names=("downstream_orders",),
            expected_rows=((1, 155),),
        )
    ],
    ids=["backward dbt source freshness movement reruns downstream work"],
)
def test_given_dbt_source_freshness_moves_backward_when_building_then_reruns_downstream_work(
    test_case: DbtPhase11FreshnessEdgeCaseTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_phase11.duckdb"
    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert first_result.returncode == 0, first_result.stderr or first_result.stdout
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE OR REPLACE TABLE main.raw_orders AS "
            "SELECT 1 AS order_id, 10 AS customer_id, 155 AS amount, "
            "TIMESTAMP '2998-12-31 00:00:00' AS loaded_at"
        ),
    )

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--json", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert plan_result.returncode == 0, plan_result.stderr or plan_result.stdout
    plan_payload: dict[str, object] = load_json_stdout(plan_result.stdout)
    dbt_payload: Mapping[str, object] = cast(Mapping[str, object], plan_payload["dbt"])
    model_plan: Mapping[str, object] = cast(Mapping[str, object], dbt_payload["model_plan"])
    assert model_plan["run_unique_ids"] == list(test_case.expected_run_unique_ids)
    assert model_plan["stale_sqlbuild_model_names"] == list(
        test_case.expected_stale_sqlbuild_model_names
    )
    entries: list[object] = cast(list[object], model_plan["entries"])
    run_entries: tuple[Mapping[str, object], ...] = tuple(
        cast(Mapping[str, object], entry)
        for entry in entries
        if cast(Mapping[str, object], entry)["action"] == "run"
    )
    assert tuple(entry["reason"] for entry in run_entries) == test_case.expected_run_reasons

    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert changed_result.returncode == 0, changed_result.stderr or changed_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id, downstream_amount FROM main.downstream_orders ORDER BY order_id",
    ) == list(test_case.expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11FreshnessEdgeCaseTestCase(
            description="missing dbt source table is unknown and plan does not crash",
            expected_run_unique_ids=(
                "model.analytics.fact_orders",
                "model.analytics.stg_orders",
            ),
            expected_stale_sqlbuild_model_names=("downstream_orders",),
        )
    ],
    ids=["missing dbt source table is unknown and plan does not crash"],
)
def test_given_missing_dbt_source_table_when_planning_then_source_freshness_is_unknown(
    test_case: DbtPhase11FreshnessEdgeCaseTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_phase11.duckdb"
    execute_duckdb(db_path=db_path, sql="DROP TABLE main.raw_orders")

    plan_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--json", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )

    assert plan_result.returncode == test_case.expected_returncode, (
        plan_result.stderr or plan_result.stdout
    )
    plan_payload: dict[str, object] = load_json_stdout(plan_result.stdout)
    dbt_payload: Mapping[str, object] = cast(Mapping[str, object], plan_payload["dbt"])
    model_plan: Mapping[str, object] = cast(Mapping[str, object], dbt_payload["model_plan"])
    assert model_plan["run_unique_ids"] == list(test_case.expected_run_unique_ids)
    assert model_plan["stale_sqlbuild_model_names"] == list(
        test_case.expected_stale_sqlbuild_model_names
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11FreshnessEdgeCaseTestCase(
            description="custom SQLBuild target schema receives dbt source freshness state",
            expected_source_freshness_rows=(
                ("source.analytics.raw.orders", "2999-01-01T00:00:00"),
            ),
            expected_rows=((1, 100),),
        )
    ],
    ids=["custom SQLBuild target schema receives dbt source freshness state"],
)
def test_given_custom_sqlbuild_target_schema_when_building_then_writes_freshness_state_there(
    test_case: DbtPhase11FreshnessEdgeCaseTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "dbt_phase11.duckdb"
    set_dbt_phase11_sqlbuild_target_schema(project_dir=project_dir, schema="analytics_state")

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr or result.stdout
    assert query_dbt_phase11_schema_source_freshness_rows(
        project_dir=project_dir, schema="analytics_state"
    ) == list(test_case.expected_source_freshness_rows)
    assert (
        query_dbt_phase11_schema_source_freshness_rows(project_dir=project_dir, schema="main") == []
    )
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT order_id, downstream_amount "
            "FROM analytics_state.downstream_orders ORDER BY order_id"
        ),
    ) == list(test_case.expected_rows)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtPhase11FreshnessEdgeCaseTestCase(
            description="failed SQLBuild execution does not persist dbt freshness state",
            expected_returncode=1,
            expected_stdout_fragments=("dbt execution", "SQLBuild execution"),
            expected_source_freshness_rows=(),
        )
    ],
    ids=["failed SQLBuild execution does not persist dbt freshness state"],
)
def test_given_sqlbuild_execution_fails_after_dbt_when_building_then_does_not_write_freshness_state(
    test_case: DbtPhase11FreshnessEdgeCaseTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    write_dbt_phase11_invalid_downstream_model(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr or result.stdout
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    assert query_dbt_phase11_source_freshness_rows(project_dir=project_dir) == list(
        test_case.expected_source_freshness_rows
    )


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
        command=("dbt", "build", "--select", "+downstream_orders", "+customer_summary"),
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
                "+downstream_orders",
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
        command=(
            "dbt",
            "build",
            "--select",
            "+downstream_orders",
            "+customer_summary",
            "country_codes",
        ),
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
                "+downstream_orders",
                "country_codes",
                "not_null_fact_orders_order_id",
            ),
            expected_stdout_fragments=(
                "Non-model dbt work",
                "Seeds (1, changed)",
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
        command=("dbt", "build", "--select", "+downstream_orders", "+customer_summary"),
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
        command=("dbt", "build", "--select", "+downstream_orders", "+customer_summary"),
        project_dir=project_dir,
    )
    assert setup_result.returncode == 0, setup_result.stderr or setup_result.stdout
    add_dbt_phase11_sqlbuild_function_branch(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+amount_quality", "+customer_summary"),
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
            expected_stdout_fragments=("Skipped current models",),
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
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert build_result.returncode == 0, build_result.stderr or build_result.stdout

    json_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--json", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert json_result.returncode == 0, json_result.stderr or json_result.stdout
    payload: dict[str, object] = load_json_stdout(json_result.stdout)
    dbt_payload: Mapping[str, object] = cast(Mapping[str, object], payload["dbt"])
    model_plan: Mapping[str, object] = cast(Mapping[str, object], dbt_payload["model_plan"])
    assert model_plan["current_unique_ids"] == list(test_case.expected_current_unique_ids)

    human_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "plan", "--select", "+downstream_orders"),
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
            expected_stdout_fragments=("dbt execution", "SQLBuild execution"),
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
        command=("dbt", "build", "--select", "+downstream_orders"),
        project_dir=project_dir,
    )
    assert first_result.returncode == 0, first_result.stderr or first_result.stdout
    write_dbt_phase11_fact_orders_model(
        project_dir=project_dir,
        amount_expression="amount + 7",
    )

    changed_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+downstream_orders"),
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


FULL_REFRESH_SCOPE_TEST_CASES: list[DbtFullRefreshScopeTestCase] = [
    DbtFullRefreshScopeTestCase(
        description="full-refresh of a leaf selects only that model, not its upstream",
        select="fact_orders",
        expected_command_select_fragments=("fqn:analytics.fact_orders",),
        unexpected_command_select_fragments=("fqn:analytics.stg_orders",),
        expected_full_refresh_count=1,
    ),
    DbtFullRefreshScopeTestCase(
        description="full-refresh of a closure selects the whole upstream closure",
        select="+fact_orders",
        expected_command_select_fragments=(
            "fqn:analytics.fact_orders",
            "fqn:analytics.stg_orders",
        ),
        unexpected_command_select_fragments=(),
        expected_full_refresh_count=2,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    FULL_REFRESH_SCOPE_TEST_CASES,
    ids=[case.description for case in FULL_REFRESH_SCOPE_TEST_CASES],
)
def test_given_full_refresh_when_selecting_then_scope_matches_selection(
    test_case: DbtFullRefreshScopeTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    setup: subprocess.CompletedProcess[str] = run_sqb(
        command=("dbt", "build", "--select", "+fact_orders"),
        project_dir=project_dir,
    )
    assert setup.returncode == 0, setup.stderr or setup.stdout

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", test_case.select, "--full-refresh"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert f"Full refresh ({test_case.expected_full_refresh_count})" in result.stdout
    command_line: str = next(
        line for line in result.stdout.splitlines() if "dbt build" in line and "--select" in line
    )
    fragment: str
    for fragment in test_case.expected_command_select_fragments:
        assert fragment in command_line
    unexpected: str
    for unexpected in test_case.unexpected_command_select_fragments:
        assert unexpected not in command_line
