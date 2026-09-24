"""Integration coverage for manual migrate_from migrations through the real CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations._test_types import (
    BackAndForthMigrationTestCase,
    MigrationCompatibilityTestCase,
    MigrationCompileErrorTestCase,
    MigrationInterruptionTestCase,
    MigrationOutcomeTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    DESTINATION_MODEL,
    ORIGIN_MODEL,
    CliRun,
    build,
    build_ok,
    build_origin,
    execute,
    fail_after_migrations,
    fail_clone,
    fail_record,
    incremental_orders_sql,
    load_raw_orders,
    migration_decisions,
    migration_events,
    model_entry,
    order_ids,
    plan_json,
    query,
    relation_names,
    rename_model,
    run_sqb,
    snapshot_orders_sql,
    write_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationOutcomeTestCase(
            description="first migration clones eight days of history",
            expected_decisions=("migrate",),
            expected_events=(("stg_orders", "stg_customer_orders", "migrate"),),
            expected_destination_ids=tuple(range(1, 9)),
            expected_output_fragment="Migrated main.stg_orders -> main.stg_customer_orders",
            expected_reason="normal_incremental",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_incremental_when_building_then_history_is_cloned_and_recorded(
    test_case: MigrationOutcomeTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_origin(project_dir=tmp_path, capsys=capsys)
    load_raw_orders(project_dir=tmp_path, first_day=4, last_day=8)
    rename_model(project_dir=tmp_path, name=DESTINATION_MODEL, migrate_from=ORIGIN_MODEL)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    result: CliRun = build_ok(project_dir=tmp_path, capsys=capsys)

    assert migration_decisions(plan) == test_case.expected_decisions
    assert plan["migrations"][0]["compatibility"] == "compatible"
    assert model_entry(plan=plan, name=DESTINATION_MODEL)["reason"] == test_case.expected_reason
    assert model_entry(plan=plan, name=DESTINATION_MODEL)["action"] == "incremental_delete_insert"
    assert test_case.expected_output_fragment in result.output
    assert (
        order_ids(project_dir=tmp_path, relation=f"main.{DESTINATION_MODEL}")
        == test_case.expected_destination_ids
    )
    assert order_ids(project_dir=tmp_path, relation=f"main.{ORIGIN_MODEL}") == tuple(range(1, 6))
    assert migration_events(project_dir=tmp_path) == test_case.expected_events


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationOutcomeTestCase(
            description="completed forced migration is skipped with a removal hint",
            expected_decisions=("done",),
            expected_events=(("stg_orders", "stg_customer_orders", "migrate"),),
            expected_destination_ids=tuple(range(1, 8)),
            expected_output_fragment="migrate_from can be removed from 'stg_customer_orders'",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_completed_migration_when_rebuilding_then_warns_and_skips(
    test_case: MigrationOutcomeTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_origin(project_dir=tmp_path, capsys=capsys)
    rename_model(
        project_dir=tmp_path, name=DESTINATION_MODEL, migrate_from=ORIGIN_MODEL, migrate_force=True
    )
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=7)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    result: CliRun = build_ok(project_dir=tmp_path, capsys=capsys)

    assert migration_decisions(plan) == test_case.expected_decisions
    assert test_case.expected_output_fragment in result.output
    assert "Migrating" not in result.output
    assert migration_events(project_dir=tmp_path) == test_case.expected_events
    assert (
        order_ids(project_dir=tmp_path, relation=f"main.{DESTINATION_MODEL}")
        == test_case.expected_destination_ids
    )


@pytest.mark.parametrize(
    "test_case",
    [
        BackAndForthMigrationTestCase(
            description="day one, five, and nine renames",
            expected_day_decisions=(
                ("migrate",),
                ("superseded_replace",),
                ("superseded_replace",),
            ),
            expected_day_five_ids=tuple(range(1, 7)),
            expected_final_ids=tuple(range(1, 10)),
            expected_events=(
                ("stg_orders", "stg_customer_orders", "migrate"),
                ("stg_customer_orders", "stg_orders", "superseded_replace"),
                ("stg_orders", "stg_customer_orders", "superseded_replace"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_back_and_forth_renames_when_building_each_day_then_every_move_converges(
    test_case: BackAndForthMigrationTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(project_dir=tmp_path, models={ORIGIN_MODEL: incremental_orders_sql()})
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=4)
    rename_model(project_dir=tmp_path, name=DESTINATION_MODEL, migrate_from=ORIGIN_MODEL)
    day_one: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=6)
    rename_model(project_dir=tmp_path, name=ORIGIN_MODEL, migrate_from=DESTINATION_MODEL)
    day_five: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    after_day_five: tuple[int, ...] = order_ids(
        project_dir=tmp_path, relation=f"main.{ORIGIN_MODEL}"
    )

    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=9)
    rename_model(project_dir=tmp_path, name=DESTINATION_MODEL, migrate_from=ORIGIN_MODEL)
    day_nine: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert (
        migration_decisions(day_one),
        migration_decisions(day_five),
        migration_decisions(day_nine),
    ) == test_case.expected_day_decisions
    assert after_day_five == test_case.expected_day_five_ids
    assert (
        order_ids(project_dir=tmp_path, relation=f"main.{DESTINATION_MODEL}")
        == test_case.expected_final_ids
    )
    assert migration_events(project_dir=tmp_path) == test_case.expected_events


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationOutcomeTestCase(
            description="unrecorded destination conflicts until migrate_force replaces it",
            expected_decisions=("conflict", "forced_replace", "done"),
            expected_events=(("stg_orders", "stg_customer_orders", "forced_replace"),),
            expected_destination_ids=tuple(range(1, 6)),
            expected_output_fragment="model migration conflict",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unrecorded_existing_destination_when_building_then_conflict_until_forced(
    test_case: MigrationOutcomeTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_origin(project_dir=tmp_path, capsys=capsys)
    execute(
        project_dir=tmp_path,
        sql=(
            f"CREATE TABLE main.{DESTINATION_MODEL} AS SELECT 999 AS order_id, "
            "TIMESTAMP '2026-01-01' AS order_date, 1 AS amount_cents"
        ),
    )
    rename_model(project_dir=tmp_path, name=DESTINATION_MODEL, migrate_from=ORIGIN_MODEL)

    conflict_plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    conflict: CliRun = build(project_dir=tmp_path, capsys=capsys)
    preserved: tuple[int, ...] = order_ids(
        project_dir=tmp_path, relation=f"main.{DESTINATION_MODEL}"
    )
    rename_model(
        project_dir=tmp_path, name=DESTINATION_MODEL, migrate_from=ORIGIN_MODEL, migrate_force=True
    )
    forced_plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    after_force: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)

    assert (
        migration_decisions(conflict_plan)
        + migration_decisions(forced_plan)
        + migration_decisions(after_force)
    ) == test_case.expected_decisions
    assert conflict.exit_code == 1
    assert test_case.expected_output_fragment in conflict.output
    assert preserved == (999,)
    assert (
        order_ids(project_dir=tmp_path, relation=f"main.{DESTINATION_MODEL}")
        == test_case.expected_destination_ids
    )
    assert migration_events(project_dir=tmp_path) == test_case.expected_events


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationOutcomeTestCase(
            description="missing origin builds without history and records nothing",
            expected_decisions=("origin_missing",),
            expected_destination_ids=(1, 2, 3),
            expected_output_fragment="does not exist",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_origin_when_building_then_warns_and_builds_without_history(
    test_case: MigrationOutcomeTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(
        project_dir=tmp_path,
        models={DESTINATION_MODEL: incremental_orders_sql(migrate_from="retired_orders")},
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    result: CliRun = build_ok(project_dir=tmp_path, capsys=capsys)

    assert migration_decisions(plan) == test_case.expected_decisions
    assert test_case.expected_output_fragment in result.output
    assert (
        order_ids(project_dir=tmp_path, relation=f"main.{DESTINATION_MODEL}")
        == test_case.expected_destination_ids
    )
    assert "_sqlbuild_migrations" not in relation_names(project_dir=tmp_path, schema="main")


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationOutcomeTestCase(
            description="replay_on_change full does not replay after the handover",
            expected_decisions=("migrate",),
            expected_destination_ids=tuple(range(1, 7)),
            expected_reason="normal_incremental",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_replay_on_change_full_when_migrating_then_destination_is_not_replayed(
    test_case: MigrationOutcomeTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(
        project_dir=tmp_path,
        models={ORIGIN_MODEL: incremental_orders_sql(extra_config="  replay_on_change full,\n")},
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=5)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    load_raw_orders(project_dir=tmp_path, first_day=5, last_day=6)
    rename_model(
        project_dir=tmp_path,
        name=DESTINATION_MODEL,
        migrate_from=ORIGIN_MODEL,
        extra_config="  replay_on_change full,\n",
    )

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    second_plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)

    assert migration_decisions(plan) == test_case.expected_decisions
    assert model_entry(plan=plan, name=DESTINATION_MODEL)["reason"] == test_case.expected_reason
    assert model_entry(plan=plan, name=DESTINATION_MODEL)["action"] != "create_table"
    assert (
        model_entry(plan=second_plan, name=DESTINATION_MODEL)["reason"] == test_case.expected_reason
    )
    assert (
        order_ids(project_dir=tmp_path, relation=f"main.{DESTINATION_MODEL}")
        == test_case.expected_destination_ids
    )


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
            model_sql=incremental_orders_sql(migrate_from=DESTINATION_MODEL),
            expected_fragment="migrate_from cannot name the model itself",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_migration_header_when_compiling_then_fails(
    test_case: MigrationCompileErrorTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(project_dir=tmp_path, models={DESTINATION_MODEL: test_case.model_sql})

    result: CliRun = run_sqb(project_dir=tmp_path, args=("compile",), capsys=capsys)

    assert result.exit_code == 1
    assert test_case.expected_fragment in result.output


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationOutcomeTestCase(
            description="snapshot history rows move to the renamed snapshot",
            expected_decisions=("migrate",),
            expected_events=(("order_snapshot", "order_history", "migrate"),),
            expected_destination_ids=(1, 2, 3),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_model_when_migrating_then_history_rows_are_preserved(
    test_case: MigrationOutcomeTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(
        project_dir=tmp_path, models={"order_snapshot": snapshot_orders_sql(migration_lines="")}
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    write_project(
        project_dir=tmp_path,
        models={
            "order_history": snapshot_orders_sql(
                migration_lines='  migrate_from "order_snapshot",\n'
            )
        },
    )

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert migration_decisions(plan) == test_case.expected_decisions
    assert (
        order_ids(project_dir=tmp_path, relation="main.order_history")
        == test_case.expected_destination_ids
    )
    assert migration_events(project_dir=tmp_path) == test_case.expected_events


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
            DESTINATION_MODEL: incremental_orders_sql(
                migrate_from="main.legacy_orders",
                extra_config=test_case.destination_extra_config,
                select_sql=test_case.destination_select_sql,
            )
        },
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    execute(project_dir=tmp_path, sql=test_case.origin_setup_sql)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    result: CliRun = build(project_dir=tmp_path, capsys=capsys)

    assert plan["migrations"][0]["compatibility"] == test_case.expected_compatibility
    assert result.exit_code == test_case.expected_build_exit_code, result.output
    assert test_case.expected_fragment in result.output
    assert query(project_dir=tmp_path, sql="SELECT count(*) FROM main.legacy_orders") == [(1,)]


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationInterruptionTestCase(
            description="failure while cloning redoes the move",
            install_failure=fail_clone,
            rerun_with_force=False,
            expected_first_exit_code=1,
            expected_decision_after_failure="migrate",
            expected_final_decisions=("migrate",),
        ),
        MigrationInterruptionTestCase(
            description="crash before recording leaves an unrecorded destination",
            install_failure=fail_record,
            rerun_with_force=True,
            expected_first_exit_code=1,
            expected_decision_after_failure="conflict",
            expected_final_decisions=("forced_replace",),
        ),
        MigrationInterruptionTestCase(
            description="crash after recording continues from the migrated history",
            install_failure=fail_after_migrations,
            rerun_with_force=False,
            expected_first_exit_code=1,
            expected_decision_after_failure="done",
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
    build_origin(project_dir=tmp_path, capsys=capsys)
    load_raw_orders(project_dir=tmp_path, first_day=4, last_day=7)
    rename_model(project_dir=tmp_path, name=DESTINATION_MODEL, migrate_from=ORIGIN_MODEL)

    with monkeypatch.context() as patch:
        test_case.install_failure(patch)
        interrupted: CliRun = build(project_dir=tmp_path, capsys=capsys)
    after_failure: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    rename_model(
        project_dir=tmp_path,
        name=DESTINATION_MODEL,
        migrate_from=ORIGIN_MODEL,
        migrate_force=test_case.rerun_with_force,
    )
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    converged: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)

    assert interrupted.exit_code == test_case.expected_first_exit_code, interrupted.output
    assert migration_decisions(after_failure) == (test_case.expected_decision_after_failure,)
    assert migration_decisions(converged) == ("done",)
    assert model_entry(plan=converged, name=DESTINATION_MODEL)["reason"] == "normal_incremental"
    assert order_ids(project_dir=tmp_path, relation=f"main.{DESTINATION_MODEL}") == tuple(
        range(1, 8)
    )
    assert order_ids(project_dir=tmp_path, relation=f"main.{ORIGIN_MODEL}") == tuple(range(1, 6))
    assert tuple(event[2] for event in migration_events(project_dir=tmp_path)) == (
        test_case.expected_final_decisions
    )


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationOutcomeTestCase(
            description="crash before recording a superseded replace repeats the replace",
            expected_decisions=("superseded_replace",),
            expected_events=(
                ("stg_orders", "stg_customer_orders", "migrate"),
                ("stg_customer_orders", "stg_orders", "superseded_replace"),
            ),
            expected_destination_ids=tuple(range(1, 6)),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_interrupted_superseded_replace_when_rerunning_then_replaces_again(
    test_case: MigrationOutcomeTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_project(project_dir=tmp_path, models={ORIGIN_MODEL: incremental_orders_sql()})
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=5)
    rename_model(project_dir=tmp_path, name=DESTINATION_MODEL, migrate_from=ORIGIN_MODEL)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    rename_model(project_dir=tmp_path, name=ORIGIN_MODEL, migrate_from=DESTINATION_MODEL)

    with monkeypatch.context() as patch:
        fail_record(patch)
        interrupted: CliRun = build(project_dir=tmp_path, capsys=capsys)
    after_failure: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert interrupted.exit_code == 1
    assert migration_decisions(after_failure) == test_case.expected_decisions
    assert (
        order_ids(project_dir=tmp_path, relation=f"main.{ORIGIN_MODEL}")
        == test_case.expected_destination_ids
    )
    assert migration_events(project_dir=tmp_path) == test_case.expected_events


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
