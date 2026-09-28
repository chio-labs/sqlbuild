"""Integration coverage for in-place column renames through the real CLI on DuckDB."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.column_migrations._test_types import (
    ColumnRenameOutcomeTestCase,
    CompletedColumnRenameTestCase,
    CursorColumnRenameTestCase,
    FirstRunDeclarationTestCase,
    NearMatchPolicyTestCase,
    RenameWithPolicyTestCase,
    SnapshotColumnRenameTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.column_migrations.helpers import (
    MICROBATCH_CONFIG,
    RELATION,
    REPLAY_FULL,
    CliRun,
    build_initial,
    build_ok,
    change_historical_amount,
    column_events,
    column_names,
    column_values,
    last_visible_line,
    load_orders,
    migrate_columns,
    model_plan,
    orders_sql,
    plan_json,
    plan_text,
    planned_column_migrations,
    snapshot_sql,
    state_table_names,
    warning_codes,
    write_model,
)
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    execute,
    query,
)

_HISTORY: tuple[tuple[int, Any], ...] = ((1, 101), (2, 102), (3, 103), (4, 104), (5, 105))


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnRenameOutcomeTestCase(
            description="declared rename keeps history without replay",
            renamed_sql=orders_sql(
                columns="amount AS revenue",
                extra_config=REPLAY_FULL + migrate_columns("revenue (migrate_from amount)"),
            ),
            expected_planned=(("amount", "revenue", "manual", "rename"),),
            expected_plan_fragment=(
                "Column migrations (1)\n└── fct_orders  migrate columns\n"
                "    └── amount -> revenue  rename in place\n"
            ),
            expected_columns=("order_id", "order_date", "revenue"),
            expected_values=_HISTORY,
            expected_events=(("amount", "revenue", "manual", "rename"),),
        ),
        ColumnRenameOutcomeTestCase(
            description="pure rename is detected automatically",
            renamed_sql=orders_sql(columns="amount AS revenue", extra_config=REPLAY_FULL),
            expected_planned=(("amount", "revenue", "automatic", "rename"),),
            expected_plan_fragment=(
                "Column migrations (1)\n└── fct_orders  migrate columns\n"
                "    └── amount -> revenue  rename in place  (automatic)\n"
            ),
            expected_columns=("order_id", "order_date", "revenue"),
            expected_values=_HISTORY,
            expected_events=(("amount", "revenue", "automatic", "rename"),),
        ),
        ColumnRenameOutcomeTestCase(
            description="declared near match renames and follows replay for the new expression",
            renamed_sql=orders_sql(
                columns="amount * 10 AS revenue",
                extra_config=migrate_columns("revenue (migrate_from amount)"),
            ),
            expected_planned=(("amount", "revenue", "manual", "rename"),),
            expected_plan_fragment="    └── amount -> revenue  rename in place\n",
            expected_columns=("order_id", "order_date", "revenue"),
            expected_values=((1, 101), (2, 102), (3, 1030), (4, 1040), (5, 1050)),
            expected_events=(("amount", "revenue", "manual", "rename"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_column_when_building_then_history_moves_to_the_new_name(
    test_case: ColumnRenameOutcomeTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_initial(project_dir=tmp_path, capsys=capsys)
    write_model(project_dir=tmp_path, sql=test_case.renamed_sql)
    change_historical_amount(project_dir=tmp_path)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    text: str = plan_text(project_dir=tmp_path, capsys=capsys)
    result: CliRun = build_ok(project_dir=tmp_path, capsys=capsys)

    assert planned_column_migrations(plan) == test_case.expected_planned
    assert test_case.expected_plan_fragment in text
    assert "Renamed columns of main.fct_orders (amount -> revenue)" in result.output
    assert column_names(project_dir=tmp_path) == test_case.expected_columns
    assert (
        column_values(project_dir=tmp_path, column=test_case.value_column)
        == test_case.expected_values
    )
    assert column_events(project_dir=tmp_path) == test_case.expected_events


@pytest.mark.parametrize(
    "test_case",
    [
        RenameWithPolicyTestCase(
            description="pure rename with a full replay policy is not replayed",
            renamed_sql=orders_sql(columns="amount AS revenue", extra_config=REPLAY_FULL),
            expected_columns=("order_id", "order_date", "revenue"),
            expected_values=_HISTORY,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_pure_rename_with_replay_policy_when_planning_then_model_continues_forward(
    test_case: RenameWithPolicyTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_initial(project_dir=tmp_path, capsys=capsys)
    write_model(project_dir=tmp_path, sql=test_case.renamed_sql)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert model_plan(plan)["reason"] == "normal_incremental"
    assert model_plan(plan)["backfill"]["action"] == "forward"
    assert column_names(project_dir=tmp_path) == test_case.expected_columns
    assert column_values(project_dir=tmp_path, column="revenue") == test_case.expected_values


@pytest.mark.parametrize(
    "test_case",
    [
        RenameWithPolicyTestCase(
            description="append_new_columns renames first, then adds the new column",
            renamed_sql=orders_sql(columns="amount AS revenue, tax * 2 AS double_tax"),
            expected_columns=("order_id", "order_date", "revenue", "double_tax"),
            expected_values=_HISTORY,
            added_column="double_tax",
            expected_added_values=((1, None), (2, None), (3, 6), (4, 8), (5, 10)),
        ),
        RenameWithPolicyTestCase(
            description="fail accepts a pure rename because no difference remains",
            renamed_sql=orders_sql(
                columns="amount AS revenue", extra_config="  on_schema_change fail,\n"
            ),
            expected_columns=("order_id", "order_date", "revenue"),
            expected_values=_HISTORY,
        ),
        RenameWithPolicyTestCase(
            description="sync_all_columns renames first, then drops the removed column",
            renamed_sql=orders_sql(
                columns="amount AS revenue",
                extra_config="  on_schema_change sync_all_columns,\n",
            ),
            expected_columns=("order_id", "order_date", "revenue"),
            expected_values=_HISTORY,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rename_and_schema_policy_when_building_then_rename_runs_before_the_policy(
    test_case: RenameWithPolicyTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_initial(project_dir=tmp_path, capsys=capsys, sql=orders_sql())
    write_model(project_dir=tmp_path, sql=test_case.renamed_sql)

    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert column_names(project_dir=tmp_path) == test_case.expected_columns
    assert column_values(project_dir=tmp_path, column="revenue") == test_case.expected_values
    assert (
        column_values(project_dir=tmp_path, column=test_case.added_column)
        == test_case.expected_added_values
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CompletedColumnRenameTestCase(
            description="recorded declared rename reports that migrate_from can be removed",
            renamed_sql=orders_sql(
                columns="amount AS revenue",
                extra_config=migrate_columns("revenue (migrate_from amount)"),
            ),
            expected_planned=(("amount", "revenue", "manual", "done"),),
            expected_notice=("migrate_from can be removed from column 'revenue' of 'fct_orders'"),
            expected_final_line="Completed successfully",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_rename_when_rebuilding_then_notice_precedes_the_success_line(
    test_case: CompletedColumnRenameTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_initial(project_dir=tmp_path, capsys=capsys)
    write_model(project_dir=tmp_path, sql=test_case.renamed_sql)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    result: CliRun = build_ok(project_dir=tmp_path, capsys=capsys)

    assert planned_column_migrations(plan) == test_case.expected_planned
    assert "M108" in warning_codes(plan)
    assert result.stdout.count(test_case.expected_notice) == 1
    assert test_case.expected_final_line in last_visible_line(result.stdout)
    assert "Renaming columns" not in result.output
    assert len(column_events(project_dir=tmp_path)) == 1


@pytest.mark.parametrize(
    "test_case",
    [
        NearMatchPolicyTestCase(
            description="append_new_columns keeps the old column and adds the new one",
            renamed_sql=orders_sql(columns="ROUND(amount * 1.5, 2) AS revenue"),
            expected_hint=(
                "similar to amount; if this is a rename, add revenue (migrate_from amount)"
            ),
            expected_columns=("order_id", "order_date", "amount", "revenue"),
        ),
        NearMatchPolicyTestCase(
            description="sync_all_columns drops the old column and adds the new one",
            renamed_sql=orders_sql(
                columns="ROUND(amount * 1.5, 2) AS revenue",
                extra_config="  on_schema_change sync_all_columns,\n",
            ),
            expected_hint=(
                "similar to amount; if this is a rename, add revenue (migrate_from amount)"
            ),
            expected_columns=("order_id", "order_date", "revenue"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_near_match_when_building_then_hint_shows_once_and_policy_applies(
    test_case: NearMatchPolicyTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_initial(project_dir=tmp_path, capsys=capsys)
    write_model(project_dir=tmp_path, sql=test_case.renamed_sql)

    before: str = plan_text(project_dir=tmp_path, capsys=capsys)
    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)
    after: str = plan_text(project_dir=tmp_path, capsys=capsys)

    assert test_case.expected_hint in before
    assert "+ revenue" in before
    assert planned_column_migrations(plan) == ()
    assert model_plan(plan)["column_rename_hints"][0]["hint"] == test_case.expected_hint
    assert test_case.expected_hint not in after
    assert column_names(project_dir=tmp_path) == test_case.expected_columns
    assert not query(
        project_dir=tmp_path,
        sql="SELECT 1 FROM information_schema.tables WHERE table_name = "
        "'_sqlbuild_column_migrations'",
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotColumnRenameTestCase(
            description="snapshot history moves to the renamed column",
            renamed_sql=snapshot_sql(columns="amount AS revenue"),
            expected_planned=(("amount", "revenue", "automatic", "rename"),),
            expected_values=((1, 101), (2, 102), (2, 1102), (3, 103)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_column_rename_when_building_then_versions_keep_their_values(
    test_case: SnapshotColumnRenameTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_initial(project_dir=tmp_path, capsys=capsys, sql=snapshot_sql())
    load_orders(project_dir=tmp_path, last_day=3)
    write_model(project_dir=tmp_path, sql=test_case.renamed_sql)
    execute(
        project_dir=tmp_path,
        sql=(
            "CREATE OR REPLACE VIEW main.raw_orders AS SELECT i AS order_id, "
            "TIMESTAMP '2026-01-01' + to_days(CAST(i - 1 AS INTEGER)) "
            "+ CASE WHEN i = 2 THEN INTERVAL 1 DAY ELSE INTERVAL 0 DAY END AS order_date, "
            "CASE WHEN i = 2 THEN 1102 ELSE 100 + i END AS amount, i AS tax "
            "FROM range(1, 4) AS t(i)"
        ),
    )

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert planned_column_migrations(plan) == test_case.expected_planned
    assert "amount" not in column_names(project_dir=tmp_path)
    assert column_values(project_dir=tmp_path, column="revenue") == test_case.expected_values


@pytest.mark.parametrize(
    "test_case",
    [
        RenameWithPolicyTestCase(
            description="sequential microbatch rename keeps history and stays stateless",
            renamed_sql=orders_sql(columns="amount AS revenue", extra_config=MICROBATCH_CONFIG),
            expected_columns=("order_id", "order_date", "revenue"),
            expected_values=_HISTORY,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_microbatch_rename_when_building_then_batches_write_the_renamed_column(
    test_case: RenameWithPolicyTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_initial(
        project_dir=tmp_path, capsys=capsys, sql=orders_sql(extra_config=MICROBATCH_CONFIG)
    )
    write_model(project_dir=tmp_path, sql=test_case.renamed_sql)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert planned_column_migrations(plan) == (("amount", "revenue", "automatic", "rename"),)
    assert column_names(project_dir=tmp_path) == test_case.expected_columns
    assert column_values(project_dir=tmp_path, column="revenue") == test_case.expected_values
    assert "_sqlbuild_microbatches" not in state_table_names(project_dir=tmp_path)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorColumnRenameTestCase(
            description="renamed cursor column keeps the append watermark",
            renamed_sql=orders_sql(
                strategy="append",
                cursor="ordered_at",
                order_date="order_date AS ordered_at",
                extra_config=(
                    "  cursor_inputs (raw_orders order_date),\n"
                    + migrate_columns("ordered_at (migrate_from order_date)")
                ),
            ),
            expected_planned=(("order_date", "ordered_at", "manual", "rename"),),
            expected_order_ids=(2, 3, 4, 5),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_cursor_column_when_appending_then_no_history_is_reprocessed(
    test_case: CursorColumnRenameTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_initial(
        project_dir=tmp_path,
        capsys=capsys,
        sql=orders_sql(
            strategy="append",
            extra_config="  append_cursor_inclusive false,\n",
        ),
    )
    write_model(
        project_dir=tmp_path,
        sql=test_case.renamed_sql.replace(
            "  cursor_inputs", "  append_cursor_inclusive false,\n  cursor_inputs"
        ),
    )

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert planned_column_migrations(plan) == test_case.expected_planned
    assert model_plan(plan)["cursor_bounds"]["start"].startswith("2026-01-03")
    assert (
        tuple(
            int(row[0])
            for row in query(
                project_dir=tmp_path, sql=f"SELECT order_id FROM {RELATION} ORDER BY 1"
            )
        )
        == test_case.expected_order_ids
    )


@pytest.mark.parametrize(
    "test_case",
    [
        FirstRunDeclarationTestCase(
            description="declaration on a first build has nothing to migrate",
            model_sql=orders_sql(
                columns="amount AS revenue",
                extra_config=migrate_columns("revenue (migrate_from amount)"),
            ),
            expected_planned=(),
            expected_columns=("order_id", "order_date", "revenue"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_declaration_on_first_run_when_building_then_model_is_created_normally(
    test_case: FirstRunDeclarationTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_model(project_dir=tmp_path, sql=test_case.model_sql)
    load_orders(project_dir=tmp_path, last_day=3)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert planned_column_migrations(plan) == test_case.expected_planned
    assert column_names(project_dir=tmp_path) == test_case.expected_columns


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
