"""Integration coverage for manual migrate_from migrations through the real CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations._test_types import (
    MigrationCompatibilityTestCase,
    MigrationCompileErrorTestCase,
    MigrationInterruptionTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    CliRun,
    execute,
    incremental_orders_sql,
    load_raw_orders,
    migration_events,
    model_entry,
    order_ids,
    plan_json,
    query,
    relation_names,
    run_sqb,
    write_project,
)

_ORIGIN: str = "stg_orders"
_DESTINATION: str = "stg_customer_orders"


def _build(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> CliRun:
    try:
        return run_sqb(project_dir=project_dir, args=("build",), capsys=capsys)
    except Exception as error:
        return CliRun(exit_code=1, output=str(error))


def _build_ok(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> CliRun:
    result: CliRun = _build(project_dir=project_dir, capsys=capsys)
    assert result.exit_code == 0, result.output
    return result


def _build_origin(*, project_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_project(project_dir=project_dir, models={_ORIGIN: incremental_orders_sql()})
    load_raw_orders(project_dir=project_dir, first_day=1, last_day=5)
    _ = _build_ok(project_dir=project_dir, capsys=capsys)


def _rename(
    *,
    project_dir: Path,
    name: str,
    migrate_from: str | None,
    migrate_force: bool = False,
    extra_config: str = "",
) -> None:
    write_project(
        project_dir=project_dir,
        models={
            name: incremental_orders_sql(
                migrate_from=migrate_from, migrate_force=migrate_force, extra_config=extra_config
            )
        },
    )


def _migration_decisions(plan: dict[str, Any]) -> list[str]:
    return [migration["decision"] for migration in plan["migrations"]]


def test_given_renamed_incremental_when_building_then_history_is_cloned_and_recorded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _build_origin(project_dir=tmp_path, capsys=capsys)
    load_raw_orders(project_dir=tmp_path, first_day=4, last_day=8)
    _rename(project_dir=tmp_path, name=_DESTINATION, migrate_from=_ORIGIN)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    result: CliRun = _build_ok(project_dir=tmp_path, capsys=capsys)

    assert _migration_decisions(plan) == ["migrate"]
    assert plan["migrations"][0]["compatibility"] == "compatible"
    assert model_entry(plan=plan, name=_DESTINATION)["reason"] == "normal_incremental"
    assert model_entry(plan=plan, name=_DESTINATION)["action"] == "incremental_delete_insert"
    assert "Migrated main.stg_orders -> main.stg_customer_orders" in result.output
    assert order_ids(project_dir=tmp_path, relation=f"main.{_DESTINATION}") == list(range(1, 9))
    assert order_ids(project_dir=tmp_path, relation=f"main.{_ORIGIN}") == list(range(1, 6))
    assert migration_events(project_dir=tmp_path) == [(_ORIGIN, _DESTINATION, "migrate")]


def test_given_rename_without_migrate_from_when_planning_then_destination_is_first_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _build_origin(project_dir=tmp_path, capsys=capsys)
    _rename(project_dir=tmp_path, name=_DESTINATION, migrate_from=None)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)

    assert plan["migrations"] == []
    assert model_entry(plan=plan, name=_DESTINATION)["reason"] == "first_run"


def test_given_completed_migration_when_rebuilding_then_warns_and_skips(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _build_origin(project_dir=tmp_path, capsys=capsys)
    _rename(project_dir=tmp_path, name=_DESTINATION, migrate_from=_ORIGIN, migrate_force=True)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=7)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    result: CliRun = _build_ok(project_dir=tmp_path, capsys=capsys)

    assert _migration_decisions(plan) == ["done"]
    assert "migrate_from can be removed from 'stg_customer_orders'" in result.output
    assert "Migrating" not in result.output
    assert migration_events(project_dir=tmp_path) == [(_ORIGIN, _DESTINATION, "migrate")]
    assert order_ids(project_dir=tmp_path, relation=f"main.{_DESTINATION}") == list(range(1, 8))


def test_given_back_and_forth_renames_when_building_each_day_then_every_move_converges(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(project_dir=tmp_path, models={_ORIGIN: incremental_orders_sql()})
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)

    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=4)
    _rename(project_dir=tmp_path, name=_DESTINATION, migrate_from=_ORIGIN)
    day_one: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)

    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=6)
    _rename(project_dir=tmp_path, name=_ORIGIN, migrate_from=_DESTINATION)
    day_five: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)
    after_day_five: list[int] = order_ids(project_dir=tmp_path, relation=f"main.{_ORIGIN}")

    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=9)
    _rename(project_dir=tmp_path, name=_DESTINATION, migrate_from=_ORIGIN)
    day_nine: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)

    assert _migration_decisions(day_one) == ["migrate"]
    assert _migration_decisions(day_five) == ["superseded_replace"]
    assert _migration_decisions(day_nine) == ["superseded_replace"]
    assert after_day_five == list(range(1, 7))
    assert order_ids(project_dir=tmp_path, relation=f"main.{_DESTINATION}") == list(range(1, 10))
    assert migration_events(project_dir=tmp_path) == [
        (_ORIGIN, _DESTINATION, "migrate"),
        (_DESTINATION, _ORIGIN, "superseded_replace"),
        (_ORIGIN, _DESTINATION, "superseded_replace"),
    ]


def test_given_unrecorded_existing_destination_when_building_then_conflict_until_forced(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _build_origin(project_dir=tmp_path, capsys=capsys)
    execute(
        project_dir=tmp_path,
        sql=(
            f"CREATE TABLE main.{_DESTINATION} AS SELECT 999 AS order_id, "
            "TIMESTAMP '2026-01-01' AS order_date, 1 AS amount_cents"
        ),
    )
    _rename(project_dir=tmp_path, name=_DESTINATION, migrate_from=_ORIGIN)

    conflict_plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    conflict: CliRun = _build(project_dir=tmp_path, capsys=capsys)
    preserved: list[int] = order_ids(project_dir=tmp_path, relation=f"main.{_DESTINATION}")
    _rename(project_dir=tmp_path, name=_DESTINATION, migrate_from=_ORIGIN, migrate_force=True)
    forced_plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)
    after_force: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)

    assert _migration_decisions(conflict_plan) == ["conflict"]
    assert conflict.exit_code == 1
    assert "model migration conflict" in conflict.output
    assert preserved == [999]
    assert _migration_decisions(forced_plan) == ["forced_replace"]
    assert _migration_decisions(after_force) == ["done"]
    assert order_ids(project_dir=tmp_path, relation=f"main.{_DESTINATION}") == list(range(1, 6))
    assert migration_events(project_dir=tmp_path) == [(_ORIGIN, _DESTINATION, "forced_replace")]


def test_given_missing_origin_when_building_then_warns_and_builds_without_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(
        project_dir=tmp_path,
        models={_DESTINATION: incremental_orders_sql(migrate_from="retired_orders")},
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    result: CliRun = _build_ok(project_dir=tmp_path, capsys=capsys)

    assert _migration_decisions(plan) == ["origin_missing"]
    assert "does not exist" in result.output
    assert order_ids(project_dir=tmp_path, relation=f"main.{_DESTINATION}") == [1, 2, 3]
    assert "_sqlbuild_migrations" not in relation_names(project_dir=tmp_path, schema="main")


def test_given_replay_on_change_full_when_migrating_then_destination_is_not_replayed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(
        project_dir=tmp_path,
        models={_ORIGIN: incremental_orders_sql(extra_config="  replay_on_change full,\n")},
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=5)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)
    load_raw_orders(project_dir=tmp_path, first_day=5, last_day=6)
    _rename(
        project_dir=tmp_path,
        name=_DESTINATION,
        migrate_from=_ORIGIN,
        extra_config="  replay_on_change full,\n",
    )

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)
    second_plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)

    assert model_entry(plan=plan, name=_DESTINATION)["reason"] == "normal_incremental"
    assert model_entry(plan=plan, name=_DESTINATION)["action"] != "create_table"
    assert model_entry(plan=second_plan, name=_DESTINATION)["reason"] == "normal_incremental"
    assert order_ids(project_dir=tmp_path, relation=f"main.{_DESTINATION}") == list(range(1, 7))


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationCompileErrorTestCase(
            description="table materialization",
            model_sql='MODEL (materialized table, migrate_from "stg_orders");\nSELECT 1 AS id\n',
            expected_fragment="migrate_from is only valid for incremental and snapshot models",
        ),
        MigrationCompileErrorTestCase(
            description="view materialization",
            model_sql='MODEL (materialized view, migrate_from "stg_orders");\nSELECT 1 AS id\n',
            expected_fragment="migrate_from is only valid for incremental and snapshot models",
        ),
        MigrationCompileErrorTestCase(
            description="force without origin",
            model_sql=incremental_orders_sql(extra_config="  migrate_force true,\n"),
            expected_fragment="migrate_force requires migrate_from",
        ),
        MigrationCompileErrorTestCase(
            description="origin names the model itself",
            model_sql=incremental_orders_sql(migrate_from=_DESTINATION),
            expected_fragment="migrate_from cannot name the model itself",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_migration_header_when_compiling_then_fails(
    test_case: MigrationCompileErrorTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(project_dir=tmp_path, models={_DESTINATION: test_case.model_sql})

    result: CliRun = run_sqb(project_dir=tmp_path, args=("compile",), capsys=capsys)

    assert result.exit_code == 1
    assert test_case.expected_fragment in result.output


def test_given_snapshot_model_when_migrating_then_history_rows_are_preserved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot_sql: str = (
        "MODEL (\n"
        "  materialized snapshot,\n"
        "  unique_key [order_id],\n"
        "  snapshot_strategy timestamp,\n"
        "  updated_at order_date,\n"
        "{migration}"
        ");\n\n"
        'SELECT order_id, order_date, amount_cents FROM __source("raw_orders")\n'
    )
    write_project(
        project_dir=tmp_path, models={"order_snapshot": snapshot_sql.format(migration="")}
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)
    write_project(
        project_dir=tmp_path,
        models={
            "order_history": snapshot_sql.format(migration='  migrate_from "order_snapshot",\n')
        },
    )

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)

    assert _migration_decisions(plan) == ["migrate"]
    assert order_ids(project_dir=tmp_path, relation="main.order_history") == [1, 2, 3]
    assert migration_events(project_dir=tmp_path) == [
        ("order_snapshot", "order_history", "migrate")
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationCompatibilityTestCase(
            description="incompatible column type blocks the move",
            origin_setup_sql=(
                "CREATE TABLE main.legacy_orders AS SELECT 'A-1' AS order_id, "
                "TIMESTAMP '2026-01-01' AS order_date, 101 AS amount_cents"
            ),
            destination_extra_config="",
            destination_select_sql=(
                "SELECT CAST(order_id AS INTEGER) AS order_id, order_date, amount_cents "
                'FROM __source("raw_orders")'
            ),
            expected_compatibility="incompatible",
            expected_build_exit_code=1,
            expected_fragment="incompatible",
        ),
        MigrationCompatibilityTestCase(
            description="on_schema_change fail rejects a missing column",
            origin_setup_sql=(
                "CREATE TABLE main.legacy_orders AS SELECT 1 AS order_id, "
                "TIMESTAMP '2026-01-01' AS order_date"
            ),
            destination_extra_config="  on_schema_change fail,\n",
            destination_select_sql=(
                'SELECT order_id, order_date, amount_cents FROM __source("raw_orders")'
            ),
            expected_compatibility="incompatible",
            expected_build_exit_code=1,
            expected_fragment="on_schema_change fail",
        ),
        MigrationCompatibilityTestCase(
            description="append_new_columns accepts a new model column",
            origin_setup_sql=(
                "CREATE TABLE main.legacy_orders AS SELECT 1 AS order_id, "
                "TIMESTAMP '2026-01-01' AS order_date"
            ),
            destination_extra_config="",
            destination_select_sql=(
                'SELECT order_id, order_date, amount_cents FROM __source("raw_orders")'
            ),
            expected_compatibility="compatible",
            expected_build_exit_code=0,
            expected_fragment="Migrated main.legacy_orders -> main.stg_customer_orders",
        ),
        MigrationCompatibilityTestCase(
            description="numeric widening is compatible under sync_all_columns",
            origin_setup_sql=(
                "CREATE TABLE main.legacy_orders AS SELECT CAST(1 AS INTEGER) AS order_id, "
                "TIMESTAMP '2026-01-01' AS order_date, CAST(101 AS INTEGER) AS amount_cents"
            ),
            destination_extra_config="  on_schema_change sync_all_columns,\n",
            destination_select_sql=(
                "SELECT order_id, order_date, CAST(amount_cents AS BIGINT) AS amount_cents "
                'FROM __source("raw_orders")'
            ),
            expected_compatibility="compatible",
            expected_build_exit_code=0,
            expected_fragment="Migrated main.legacy_orders -> main.stg_customer_orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_origin_schema_when_migrating_then_normal_incremental_rules_decide(
    test_case: MigrationCompatibilityTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_project(
        project_dir=tmp_path,
        models={
            _DESTINATION: incremental_orders_sql(
                migrate_from="main.legacy_orders",
                extra_config=test_case.destination_extra_config,
                select_sql=test_case.destination_select_sql,
            )
        },
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    execute(project_dir=tmp_path, sql=test_case.origin_setup_sql)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    result: CliRun = _build(project_dir=tmp_path, capsys=capsys)

    assert plan["migrations"][0]["compatibility"] == test_case.expected_compatibility
    assert result.exit_code == test_case.expected_build_exit_code, result.output
    assert test_case.expected_fragment in result.output
    assert query(project_dir=tmp_path, sql="SELECT count(*) FROM main.legacy_orders") == [(1,)]


def _install_failure(*, monkeypatch: pytest.MonkeyPatch, failure_point: str) -> None:
    def _raise(**_: object) -> None:
        raise RuntimeError(f"simulated interruption at {failure_point}")

    if failure_point == "clone":
        monkeypatch.setattr(
            DuckDbAdapter,
            "render_replace_with_clone",
            lambda self, *, origin, destination, origin_is_transient=False: (
                "SELECT * FROM main.simulated_missing_relation"
            ),
        )
    elif failure_point == "record":
        monkeypatch.setattr(
            "sqlbuild.executor.build.main._apply_model_migrations.write_migration_event", _raise
        )
    else:
        monkeypatch.setattr("sqlbuild.executor.build.main._execute.apply_retention_phase", _raise)


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationInterruptionTestCase(
            description="failure while cloning redoes the move",
            failure_point="clone",
            expected_first_exit_code=1,
            expected_decision_after_failure="migrate",
            rerun_with_force=False,
            expected_final_decisions=("migrate",),
        ),
        MigrationInterruptionTestCase(
            description="crash before recording leaves an unrecorded destination",
            failure_point="record",
            expected_first_exit_code=1,
            expected_decision_after_failure="conflict",
            rerun_with_force=True,
            expected_final_decisions=("forced_replace",),
        ),
        MigrationInterruptionTestCase(
            description="crash after recording continues from the migrated history",
            failure_point="build",
            expected_first_exit_code=1,
            expected_decision_after_failure="done",
            rerun_with_force=False,
            expected_final_decisions=("migrate",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interrupted_first_migration_when_rerunning_then_converges(
    test_case: MigrationInterruptionTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _build_origin(project_dir=tmp_path, capsys=capsys)
    load_raw_orders(project_dir=tmp_path, first_day=4, last_day=7)
    _rename(project_dir=tmp_path, name=_DESTINATION, migrate_from=_ORIGIN)

    with monkeypatch.context() as patch:
        _install_failure(monkeypatch=patch, failure_point=test_case.failure_point)
        interrupted: CliRun = _build(project_dir=tmp_path, capsys=capsys)
    after_failure: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _rename(
        project_dir=tmp_path,
        name=_DESTINATION,
        migrate_from=_ORIGIN,
        migrate_force=test_case.rerun_with_force,
    )
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)
    converged: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)

    assert interrupted.exit_code == test_case.expected_first_exit_code, interrupted.output
    assert _migration_decisions(after_failure) == [test_case.expected_decision_after_failure]
    assert _migration_decisions(converged) == ["done"]
    assert model_entry(plan=converged, name=_DESTINATION)["reason"] == "normal_incremental"
    assert order_ids(project_dir=tmp_path, relation=f"main.{_DESTINATION}") == list(range(1, 8))
    assert order_ids(project_dir=tmp_path, relation=f"main.{_ORIGIN}") == list(range(1, 6))
    assert tuple(event[2] for event in migration_events(project_dir=tmp_path)) == (
        test_case.expected_final_decisions
    )


def test_given_interrupted_superseded_replace_when_rerunning_then_replaces_again(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    write_project(project_dir=tmp_path, models={_ORIGIN: incremental_orders_sql()})
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=5)
    _rename(project_dir=tmp_path, name=_DESTINATION, migrate_from=_ORIGIN)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)
    _rename(project_dir=tmp_path, name=_ORIGIN, migrate_from=_DESTINATION)

    with monkeypatch.context() as patch:
        _install_failure(monkeypatch=patch, failure_point="record")
        interrupted: CliRun = _build(project_dir=tmp_path, capsys=capsys)
    after_failure: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = _build_ok(project_dir=tmp_path, capsys=capsys)

    assert interrupted.exit_code == 1
    assert _migration_decisions(after_failure) == ["superseded_replace"]
    assert order_ids(project_dir=tmp_path, relation=f"main.{_ORIGIN}") == list(range(1, 6))
    assert migration_events(project_dir=tmp_path) == [
        (_ORIGIN, _DESTINATION, "migrate"),
        (_DESTINATION, _ORIGIN, "superseded_replace"),
    ]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
