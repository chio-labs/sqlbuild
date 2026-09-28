"""PostgreSQL e2e coverage for in-place column renames of incremental models."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresColumnMigrationE2ETestCase,
    PostgresColumnMigrationRollbackE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    FACT_ORDERS_MODEL,
    build_unique_schema_name,
    cleanup_postgres_schema,
    create_unwritable_column_migration_table,
    ensure_postgres_schema_ready,
    execute_postgres_sql,
    fact_order_columns,
    fact_orders_sql,
    fetch_postgres_rows,
    load_raw_orders,
    write_migration_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

_AMOUNTS: tuple[tuple[object, ...], ...] = ((1, 101), (2, 102), (3, 103), (4, 104), (5, 105))


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresColumnMigrationE2ETestCase(
            description="automatic rename keeps history and dependent views keep reading",
            expected_columns=(("order_id",), ("order_date",), ("amount",)),
            expected_amounts=_AMOUNTS,
            expected_view_amounts=_AMOUNTS,
            expected_events=(("amount_cents", "amount", "automatic", "rename"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_column_when_building_on_postgres_then_history_keeps_its_values(
    tmp_path: Path,
    test_case: PostgresColumnMigrationE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    """ALTER TABLE ... RENAME COLUMN keeps rows, and PostgreSQL re-points dependent views."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_column_migration")
    raw_schema_name: str = f"{schema_name}_raw"
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    load_raw_orders(raw_schema_name=raw_schema_name, config=postgres_e2e_config)
    project_dir: Path = write_migration_project(
        tmp_path=tmp_path,
        schema_name=schema_name,
        raw_schema_name=raw_schema_name,
        config=postgres_e2e_config,
        models={FACT_ORDERS_MODEL: fact_orders_sql()},
    )
    try:
        initial: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        execute_postgres_sql(
            sql=(
                f"CREATE VIEW {raw_schema_name}.order_amounts AS SELECT order_id, amount_cents "
                f"FROM {schema_name}.{FACT_ORDERS_MODEL}"
            ),
            config=postgres_e2e_config,
        )
        project_dir = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={FACT_ORDERS_MODEL: fact_orders_sql(amount="amount_cents AS amount")},
        )
        renamed: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )

        assert initial.returncode == 0, initial.stdout + initial.stderr
        assert renamed.returncode == 0, renamed.stdout + renamed.stderr
        assert "amount_cents -> amount" in renamed.stdout + renamed.stderr
        assert (
            fact_order_columns(schema_name=schema_name, config=postgres_e2e_config)
            == test_case.expected_columns
        )
        assert (
            fetch_postgres_rows(
                sql=f"SELECT order_id, amount FROM {schema_name}.{FACT_ORDERS_MODEL} ORDER BY 1",
                config=postgres_e2e_config,
            )
            == test_case.expected_amounts
        )
        assert (
            fetch_postgres_rows(
                sql=f"SELECT order_id, amount_cents FROM {raw_schema_name}.order_amounts ORDER BY 1",
                config=postgres_e2e_config,
            )
            == test_case.expected_view_amounts
        )
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT origin_column, destination_column, discovery, decision "
                    f"FROM {schema_name}._sqlbuild_column_migrations"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_events
        )
    finally:
        cleanup_postgres_schema(schema_name=raw_schema_name, config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresColumnMigrationRollbackE2ETestCase(
            description="failed event insert rolls the column rename back",
            expected_failure_fragment="M113",
            expected_columns_after_failure=(("order_id",), ("order_date",), ("amount_cents",)),
            expected_final_columns=(("order_id",), ("order_date",), ("amount",)),
            expected_events=(("amount_cents", "amount", "manual", "rename"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unwritable_event_table_when_renaming_column_then_rename_rolls_back(
    tmp_path: Path,
    test_case: PostgresColumnMigrationRollbackE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    """The column rename and its event commit or roll back together on PostgreSQL."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_column_rollback")
    raw_schema_name: str = f"{schema_name}_raw"
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    load_raw_orders(raw_schema_name=raw_schema_name, config=postgres_e2e_config)
    project_dir: Path = write_migration_project(
        tmp_path=tmp_path,
        schema_name=schema_name,
        raw_schema_name=raw_schema_name,
        config=postgres_e2e_config,
        models={FACT_ORDERS_MODEL: fact_orders_sql()},
    )
    try:
        initial: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        create_unwritable_column_migration_table(
            schema_name=schema_name, config=postgres_e2e_config
        )
        project_dir = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={
                FACT_ORDERS_MODEL: fact_orders_sql(
                    amount="amount_cents AS amount", columns="amount (migrate_from amount_cents)"
                )
            },
        )
        failed: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        columns_after_failure: tuple[tuple[object, ...], ...] = fact_order_columns(
            schema_name=schema_name, config=postgres_e2e_config
        )
        execute_postgres_sql(
            sql=f"DROP VIEW {schema_name}._sqlbuild_column_migrations", config=postgres_e2e_config
        )
        retried: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )

        assert initial.returncode == 0, initial.stdout + initial.stderr
        assert failed.returncode != 0
        assert test_case.expected_failure_fragment in failed.stdout + failed.stderr
        assert columns_after_failure == test_case.expected_columns_after_failure
        assert retried.returncode == 0, retried.stdout + retried.stderr
        assert (
            fact_order_columns(schema_name=schema_name, config=postgres_e2e_config)
            == test_case.expected_final_columns
        )
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT origin_column, destination_column, discovery, decision "
                    f"FROM {schema_name}._sqlbuild_column_migrations"
                ),
                config=postgres_e2e_config,
            )
            == test_case.expected_events
        )
    finally:
        cleanup_postgres_schema(schema_name=raw_schema_name, config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
