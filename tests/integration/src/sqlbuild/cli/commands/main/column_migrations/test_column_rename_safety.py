"""Integration coverage for column rename retries, blocked renames, and header errors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.column_migrations._test_types import (
    BlockedColumnRenameTestCase,
    ColumnMigrationCompileErrorTestCase,
    ColumnRenameRecoveryTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.column_migrations.helpers import (
    REPLAY_FULL,
    CliRun,
    build,
    build_initial,
    build_ok,
    column_events,
    column_names,
    column_values,
    fail_model_build,
    fail_non_transactional_record,
    migrate_columns,
    model_plan,
    orders_sql,
    plan_json,
    planned_column_migrations,
    run_sqb,
    write_model,
)
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import execute

_HISTORY: tuple[tuple[int, Any], ...] = ((1, 101), (2, 102), (3, 103), (4, 104), (5, 105))


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnRenameRecoveryTestCase(
            description="build failure after a recorded rename resumes without replay",
            renamed_sql=orders_sql(columns="amount AS revenue", extra_config=REPLAY_FULL),
            install_failure=fail_model_build,
            expected_retry_planned=(("amount", "revenue", "automatic", "done"),),
            expected_events=(("amount", "revenue", "automatic", "rename"),),
            expected_values=_HISTORY,
        ),
        ColumnRenameRecoveryTestCase(
            description="non-transactional crash before the event records the renamed column",
            renamed_sql=orders_sql(
                columns="amount AS revenue",
                extra_config=REPLAY_FULL + migrate_columns("revenue (migrate_from amount)"),
            ),
            install_failure=fail_non_transactional_record,
            expected_retry_planned=(("amount", "revenue", "manual", "record"),),
            expected_events=(("amount", "revenue", "manual", "record"),),
            expected_values=_HISTORY,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interrupted_rename_when_retrying_then_column_is_renamed_once_and_delta_lands(
    test_case: ColumnRenameRecoveryTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_initial(project_dir=tmp_path, capsys=capsys)
    write_model(project_dir=tmp_path, sql=test_case.renamed_sql)

    with monkeypatch.context() as patched:
        test_case.install_failure(patched)
        interrupted: CliRun = build(project_dir=tmp_path, capsys=capsys)
    columns_after_interruption: tuple[str, ...] = column_names(project_dir=tmp_path)
    retry_plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    _ = build_ok(project_dir=tmp_path, capsys=capsys)

    assert interrupted.exit_code != 0
    assert columns_after_interruption == ("order_id", "order_date", "revenue")
    assert planned_column_migrations(retry_plan) == test_case.expected_retry_planned
    assert model_plan(retry_plan)["backfill"]["action"] == "forward"
    assert column_events(project_dir=tmp_path) == test_case.expected_events
    assert column_values(project_dir=tmp_path, column="revenue") == test_case.expected_values


@pytest.mark.parametrize(
    "test_case",
    [
        BlockedColumnRenameTestCase(
            description="both columns already exist",
            renamed_sql=orders_sql(
                columns="amount AS revenue",
                extra_config=migrate_columns("revenue (migrate_from amount)"),
            ),
            prepare_sql=("ALTER TABLE main.fct_orders ADD COLUMN revenue BIGINT",),
            expected_decision="conflict",
            expected_error="error[M110]",
        ),
        BlockedColumnRenameTestCase(
            description="source column never existed",
            renamed_sql=orders_sql(
                columns="amount AS revenue",
                extra_config=migrate_columns("revenue (migrate_from gross_amount)"),
            ),
            expected_decision="source_missing",
            expected_error="error[M109]",
        ),
        BlockedColumnRenameTestCase(
            description="source column is still produced",
            renamed_sql=orders_sql(
                columns="amount, amount AS revenue",
                extra_config=migrate_columns("revenue (migrate_from amount)"),
            ),
            expected_decision="still_produced",
            expected_error="error[M111]",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsafe_declared_rename_when_building_then_build_stops_before_changes(
    test_case: BlockedColumnRenameTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    build_initial(project_dir=tmp_path, capsys=capsys)
    statement: str
    for statement in test_case.prepare_sql:
        execute(project_dir=tmp_path, sql=statement)
    columns_before: tuple[str, ...] = column_names(project_dir=tmp_path)
    write_model(project_dir=tmp_path, sql=test_case.renamed_sql)

    plan: dict[str, Any] = plan_json(project_dir=tmp_path, capsys=capsys)
    result: CliRun = build(project_dir=tmp_path, capsys=capsys)

    assert [entry["decision"] for entry in plan["column_migrations"]] == [
        test_case.expected_decision
    ]
    assert result.exit_code != 0
    assert result.output.count(test_case.expected_error) == 1, result.output
    assert column_names(project_dir=tmp_path) == columns_before


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnMigrationCompileErrorTestCase(
            description="table materialization",
            model_sql=(
                "MODEL (materialized table, columns (revenue (migrate_from amount)));\n"
                'SELECT amount AS revenue FROM __source("raw_orders")\n'
            ),
            expected_fragment="only valid for incremental and snapshot models",
        ),
        ColumnMigrationCompileErrorTestCase(
            description="column migrates from itself",
            model_sql=orders_sql(
                columns="amount AS revenue",
                extra_config=migrate_columns("revenue (migrate_from revenue)"),
            ),
            expected_fragment="migrate_from cannot name the column itself",
        ),
        ColumnMigrationCompileErrorTestCase(
            description="two columns claim one source",
            model_sql=orders_sql(
                columns="amount AS revenue, amount AS gross",
                extra_config=migrate_columns(
                    "revenue (migrate_from amount), gross (migrate_from amount)"
                ),
            ),
            expected_fragment="both declare migrate_from amount",
        ),
        ColumnMigrationCompileErrorTestCase(
            description="chained renames",
            model_sql=orders_sql(
                columns="amount AS revenue, tax AS amount",
                extra_config=migrate_columns(
                    "revenue (migrate_from amount), amount (migrate_from tax)"
                ),
            ),
            expected_fragment="chained or swapped column renames are not supported",
        ),
        ColumnMigrationCompileErrorTestCase(
            description="qualified source column",
            model_sql=orders_sql(
                columns="amount AS revenue",
                extra_config=migrate_columns('revenue (migrate_from "fct_orders.amount")'),
            ),
            expected_fragment="migrate_from must name one column",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_column_migration_header_when_compiling_then_fails(
    test_case: ColumnMigrationCompileErrorTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_model(project_dir=tmp_path, sql=test_case.model_sql)

    result: CliRun = run_sqb(project_dir=tmp_path, args=("compile",), capsys=capsys)

    assert result.exit_code != 0
    assert test_case.expected_fragment in result.output, result.output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
