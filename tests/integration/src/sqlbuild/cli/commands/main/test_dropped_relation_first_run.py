"""Integration coverage for relations dropped outside SQLBuild through real CLI plans and builds."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sqlbuild.compiler.planner.constants import RECORDED_RELATION_MISSING_WARNING_CODE
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    AbsentMicrobatchFullRefreshTestCase,
    DroppedIncrementalFirstRunRangeTestCase,
    DroppedRelationRecoveryTestCase,
    DroppedSeedPlanTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    dropped_relation_microbatch_sql,
    execute_duckdb_sql,
    plan_cursor_bounds,
    plan_model,
    plan_seed_reasons,
    plan_warning_identities,
    query_duckdb_rows,
    run_build,
    run_plan_json,
    write_dropped_relation_project,
)

_INCREMENTAL_SQL: str = (
    "MODEL (\n"
    "  materialized incremental,\n"
    "  incremental_strategy delete_insert,\n"
    "  unique_key id,\n"
    "  cursor ordered_at,\n"
    "  cursor_type timestamp,\n"
    "  cursor_grain day,\n"
    "  cursor_start '2026-01-02',\n"
    ");\n\n"
    'SELECT id, ordered_at FROM __source("raw_orders")\n'
)
_TABLE_SQL: str = 'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
_MICROBATCH_CONCURRENCY_SETTINGS: str = (
    "\n[settings]\nconcurrency = 3\nmicrobatch_concurrency = true\n"
)
_BUILD_ARTIFACTS_SQL: str = (
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_name LIKE '%orders\\_\\_%' ESCAPE '\\'"
)


@pytest.mark.parametrize(
    "test_case",
    [
        DroppedRelationRecoveryTestCase(
            description="incremental table with stale delta relation",
            model_sql=_INCREMENTAL_SQL,
            drop_sql="DROP TABLE main.orders",
            stale_artifact_sql="CREATE TABLE main.orders__delta AS SELECT 99 AS id",
            expected_action="create_table",
            expected_rows=((2,), (3,)),
        ),
        DroppedRelationRecoveryTestCase(
            description="table",
            model_sql=_TABLE_SQL,
            drop_sql="DROP TABLE main.orders",
            expected_action="create_table",
            expected_rows=((1,), (2,), (3,)),
        ),
        DroppedRelationRecoveryTestCase(
            description="view",
            model_sql='MODEL (materialized view);\n\nSELECT id FROM __source("raw_orders")\n',
            drop_sql="DROP VIEW main.orders",
            expected_action="create_view",
            expected_rows=((1,), (2,), (3,)),
        ),
        DroppedRelationRecoveryTestCase(
            description="snapshot",
            model_sql=(
                "MODEL (\n"
                "  materialized snapshot,\n"
                "  unique_key [id],\n"
                "  snapshot_strategy timestamp,\n"
                "  updated_at updated_at\n"
                ");\n\n"
                'SELECT customer_id AS id, plan, updated_at FROM __source("raw_customers")\n'
            ),
            drop_sql="DROP TABLE main.orders",
            expected_action="snapshot",
            expected_rows=((1,),),
        ),
        DroppedRelationRecoveryTestCase(
            description="sequential microbatch incremental with stale delta relation",
            model_sql=dropped_relation_microbatch_sql(batch_concurrency=1),
            drop_sql="DROP TABLE main.orders",
            stale_artifact_sql="CREATE TABLE main.orders__delta AS SELECT 99 AS id",
            expected_action="create_table",
            expected_rows=((1,), (2,), (3,)),
        ),
        DroppedRelationRecoveryTestCase(
            description="concurrent microbatch incremental with recorded completions",
            model_sql=dropped_relation_microbatch_sql(batch_concurrency=3),
            drop_sql="DROP TABLE main.orders",
            settings_toml=_MICROBATCH_CONCURRENCY_SETTINGS,
            expected_action="create_table",
            expected_rows=((1,), (2,), (3,)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relation_dropped_outside_sqlbuild_when_planning_and_building_then_recreates_it(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    test_case: DroppedRelationRecoveryTestCase,
) -> None:
    db_path: Path = write_dropped_relation_project(
        project_dir=tmp_path,
        model_name="orders",
        model_sql=test_case.model_sql,
        settings_toml=test_case.settings_toml,
    )
    first_exit_code: int
    first_output: str
    first_exit_code, first_output = run_build(project_dir=tmp_path, flags=(), capsys=capsys)
    assert first_exit_code == 0, first_output
    execute_duckdb_sql(db_path=db_path, sql=test_case.drop_sql)
    execute_duckdb_sql(db_path=db_path, sql=test_case.stale_artifact_sql)

    plan: dict[str, object] = run_plan_json(project_dir=tmp_path, flags=(), capsys=capsys)
    rebuild_exit_code: int
    rebuild_output: str
    rebuild_exit_code, rebuild_output = run_build(project_dir=tmp_path, flags=(), capsys=capsys)
    rebuilt_rows: tuple[tuple[object, ...], ...] = query_duckdb_rows(
        db_path=db_path, sql="SELECT id FROM main.orders ORDER BY id"
    )
    steady_exit_code: int
    steady_output: str
    steady_exit_code, steady_output = run_build(project_dir=tmp_path, flags=(), capsys=capsys)
    steady_plan: dict[str, object] = run_plan_json(project_dir=tmp_path, flags=(), capsys=capsys)

    model: dict[str, object] = plan_model(plan=plan, name="orders")
    assert (model["action"], model["reason"]) == (test_case.expected_action, "first_run")
    assert (
        model["built_version_hash"],
        model["built_version_present"],
        model["identity_status"],
    ) == (None, False, "missing")
    assert plan_warning_identities(plan=plan) == (
        ("orders", RECORDED_RELATION_MISSING_WARNING_CODE),
    )
    assert rebuild_exit_code == 0, rebuild_output
    assert rebuilt_rows == test_case.expected_rows
    assert steady_exit_code == 0, steady_output
    assert query_duckdb_rows(db_path=db_path, sql=_BUILD_ARTIFACTS_SQL) == ()
    assert ("orders", RECORDED_RELATION_MISSING_WARNING_CODE) not in plan_warning_identities(
        plan=steady_plan
    )
    assert plan_model(plan=steady_plan, name="orders")["identity_status"] == "current"


@pytest.mark.parametrize(
    "test_case",
    [
        DroppedIncrementalFirstRunRangeTestCase(
            description="delete insert timestamp cursor restarts at cursor_start",
            model_sql=_INCREMENTAL_SQL,
            expected_start="2026-01-02T00:00:00",
            expected_end="2026-01-07T00:00:00",
            expected_rows=(
                (2, datetime(2026, 1, 2, 1)),
                (3, datetime(2026, 1, 3, 1)),
                (4, datetime(2026, 1, 5, 1)),
                (5, datetime(2026, 1, 6, 1)),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_incremental_relation_dropped_after_later_builds_when_rebuilding_then_uses_first_run_range(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    test_case: DroppedIncrementalFirstRunRangeTestCase,
) -> None:
    db_path: Path = write_dropped_relation_project(
        project_dir=tmp_path, model_name="orders", model_sql=test_case.model_sql
    )
    first_plan: dict[str, object] = run_plan_json(project_dir=tmp_path, flags=(), capsys=capsys)
    first_exit_code: int
    first_output: str
    first_exit_code, first_output = run_build(project_dir=tmp_path, flags=(), capsys=capsys)
    assert first_exit_code == 0, first_output
    execute_duckdb_sql(
        db_path=db_path, sql="INSERT INTO main.raw_orders VALUES (4, '2026-01-05 01:00:00')"
    )
    second_exit_code: int
    second_output: str
    second_exit_code, second_output = run_build(project_dir=tmp_path, flags=(), capsys=capsys)
    assert second_exit_code == 0, second_output
    execute_duckdb_sql(
        db_path=db_path,
        sql=(
            "DROP TABLE main.orders; INSERT INTO main.raw_orders VALUES (5, '2026-01-06 01:00:00')"
        ),
    )

    recreate_plan: dict[str, object] = run_plan_json(project_dir=tmp_path, flags=(), capsys=capsys)
    rebuild_exit_code: int
    rebuild_output: str
    rebuild_exit_code, rebuild_output = run_build(project_dir=tmp_path, flags=(), capsys=capsys)

    assert plan_model(plan=recreate_plan, name="orders")["reason"] == "first_run"
    assert plan_cursor_bounds(plan=first_plan, name="orders")["start"] == test_case.expected_start
    assert plan_cursor_bounds(plan=recreate_plan, name="orders") == {
        "start": test_case.expected_start,
        "end": test_case.expected_end,
    }
    assert rebuild_exit_code == 0, rebuild_output
    assert (
        query_duckdb_rows(db_path=db_path, sql="SELECT id, ordered_at FROM main.orders ORDER BY id")
        == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DroppedSeedPlanTestCase(
            description="seed with recorded fingerprint",
            model_sql=_TABLE_SQL,
            expected_steady_reasons={"order_statuses": "no_change"},
            expected_dropped_reasons={"order_statuses": "first_run"},
            expected_rows=((1,), (2,)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_seed_dropped_outside_sqlbuild_when_planning_then_reports_first_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    test_case: DroppedSeedPlanTestCase,
) -> None:
    db_path: Path = write_dropped_relation_project(
        project_dir=tmp_path, model_name="orders", model_sql=test_case.model_sql
    )
    first_exit_code: int
    first_output: str
    first_exit_code, first_output = run_build(project_dir=tmp_path, flags=(), capsys=capsys)
    assert first_exit_code == 0, first_output
    steady_plan: dict[str, object] = run_plan_json(project_dir=tmp_path, flags=(), capsys=capsys)
    execute_duckdb_sql(db_path=db_path, sql="DROP TABLE main.order_statuses")

    plan: dict[str, object] = run_plan_json(project_dir=tmp_path, flags=(), capsys=capsys)
    rebuild_exit_code: int
    rebuild_output: str
    rebuild_exit_code, rebuild_output = run_build(project_dir=tmp_path, flags=(), capsys=capsys)

    assert plan_seed_reasons(plan=steady_plan) == test_case.expected_steady_reasons
    assert plan_seed_reasons(plan=plan) == test_case.expected_dropped_reasons
    assert rebuild_exit_code == 0, rebuild_output
    assert (
        query_duckdb_rows(
            db_path=db_path,
            sql="SELECT status_code FROM main.order_statuses ORDER BY status_code",
        )
        == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        AbsentMicrobatchFullRefreshTestCase(
            description="sequential microbatch never built",
            batch_concurrency=1,
            setup_build_flags=("--select", "order_statuses"),
            setup_drop_sql="SELECT 1",
            expected_rows=((1,), (2,), (3,)),
        ),
        AbsentMicrobatchFullRefreshTestCase(
            description="sequential microbatch dropped outside sqlbuild",
            batch_concurrency=1,
            setup_build_flags=(),
            setup_drop_sql="DROP TABLE main.orders",
            expected_rows=((1,), (2,), (3,)),
        ),
        AbsentMicrobatchFullRefreshTestCase(
            description="concurrent microbatch dropped outside sqlbuild",
            batch_concurrency=3,
            setup_build_flags=(),
            setup_drop_sql="DROP TABLE main.orders",
            expected_rows=((1,), (2,), (3,)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_microbatch_target_absent_when_full_refresh_building_then_creates_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    test_case: AbsentMicrobatchFullRefreshTestCase,
) -> None:
    db_path: Path = write_dropped_relation_project(
        project_dir=tmp_path,
        model_name="orders",
        model_sql=dropped_relation_microbatch_sql(batch_concurrency=test_case.batch_concurrency),
        settings_toml=_MICROBATCH_CONCURRENCY_SETTINGS,
    )
    setup_exit_code: int
    setup_output: str
    setup_exit_code, setup_output = run_build(
        project_dir=tmp_path, flags=test_case.setup_build_flags, capsys=capsys
    )
    assert setup_exit_code == 0, setup_output
    execute_duckdb_sql(db_path=db_path, sql=test_case.setup_drop_sql)

    exit_code: int
    output: str
    exit_code, output = run_build(
        project_dir=tmp_path, flags=("--full-refresh", "--select", "orders"), capsys=capsys
    )

    assert exit_code == 0, output
    assert (
        query_duckdb_rows(db_path=db_path, sql="SELECT id FROM main.orders ORDER BY id")
        == test_case.expected_rows
    )
    assert query_duckdb_rows(db_path=db_path, sql=_BUILD_ARTIFACTS_SQL) == ()
