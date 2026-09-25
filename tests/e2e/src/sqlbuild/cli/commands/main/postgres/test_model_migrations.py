"""PostgreSQL e2e coverage for staged model migrations and identity-bound dependent views."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresMigrationRollbackE2ETestCase,
    PostgresModelMigrationE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    DESTINATION_MODEL,
    ORIGIN_MODEL,
    archive_names,
    build_unique_schema_name,
    cleanup_postgres_schema,
    create_unwritable_migration_table,
    ensure_postgres_schema_ready,
    execute_postgres_sql,
    fetch_postgres_rows,
    load_raw_orders,
    ordered_ids,
    orders_sql,
    report_view_sql,
    write_migration_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb

_TWO_ORDERS: str = " WHERE order_id <= 2"
_ALL_IDS: tuple[tuple[object, ...], ...] = ((1,), (2,), (3,), (4,), (5,))


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresModelMigrationE2ETestCase(
            description="forced replace rebinds identity-bound views and archives the old table",
            expected_destination_ids=_ALL_IDS,
            expected_view_ids=_ALL_IDS,
            expected_archive_ids=((1,), (2,)),
            expected_events=((ORIGIN_MODEL, DESTINATION_MODEL, "forced_replace"),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_views_on_destination_when_forcing_migration_then_views_follow_the_new_table(
    tmp_path: Path,
    test_case: PostgresModelMigrationE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    """Views bound by OID read the promoted table, so janitor can drop the archive."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_migration")
    raw_schema_name: str = f"{schema_name}_raw"
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    load_raw_orders(raw_schema_name=raw_schema_name, config=postgres_e2e_config)
    project_dir: Path = write_migration_project(
        tmp_path=tmp_path,
        schema_name=schema_name,
        raw_schema_name=raw_schema_name,
        config=postgres_e2e_config,
        models={
            ORIGIN_MODEL: orders_sql(),
            DESTINATION_MODEL: orders_sql(where=_TWO_ORDERS),
            "orders_report": report_view_sql(),
        },
    )
    try:
        initial: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        execute_postgres_sql(
            sql=(
                f"CREATE VIEW {raw_schema_name}.orders_dashboard AS "
                f"SELECT order_id FROM {schema_name}.{DESTINATION_MODEL}"
            ),
            config=postgres_e2e_config,
        )
        project_dir = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={
                DESTINATION_MODEL: orders_sql(migrate_from=ORIGIN_MODEL),
                "orders_report": report_view_sql(),
            },
        )
        migrated: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        archives: tuple[tuple[object, ...], ...] = archive_names(
            schema_name=schema_name, kind="migration_previous", config=postgres_e2e_config
        )
        archive_ids: tuple[tuple[object, ...], ...] = ordered_ids(
            relation=f"{schema_name}.{archives[0][0]}", config=postgres_e2e_config
        )
        janitor: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "janitor", "--auto-approve", "--retention-days", "30"),
            project_dir=project_dir,
        )

        assert initial.returncode == 0, initial.stdout + initial.stderr
        assert migrated.returncode == 0, migrated.stdout + migrated.stderr
        assert len(archives) == 1
        assert archive_ids == test_case.expected_archive_ids
        assert janitor.returncode == 0, janitor.stdout + janitor.stderr
        assert (
            archive_names(
                schema_name=schema_name, kind="migration_previous", config=postgres_e2e_config
            )
            == ()
        )
        assert (
            ordered_ids(relation=f"{schema_name}.{DESTINATION_MODEL}", config=postgres_e2e_config)
            == test_case.expected_destination_ids
        )
        assert (
            ordered_ids(relation=f"{raw_schema_name}.orders_dashboard", config=postgres_e2e_config)
            == test_case.expected_view_ids
        )
        assert (
            ordered_ids(relation=f"{schema_name}.orders_report", config=postgres_e2e_config)
            == test_case.expected_view_ids
        )
        assert (
            ordered_ids(relation=f"{schema_name}.{ORIGIN_MODEL}", config=postgres_e2e_config)
            == _ALL_IDS
        )
        assert (
            fetch_postgres_rows(
                sql=(
                    "SELECT origin_name, destination_name, decision "
                    f"FROM {schema_name}._sqlbuild_migrations"
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
        PostgresMigrationRollbackE2ETestCase(
            description="failed event insert rolls the promotion back and keeps the destination",
            expected_failure_fragment="M106",
            expected_destination_ids_after_failure=((1,), (2,)),
            expected_previous_archives_after_failure=0,
            expected_final_destination_ids=_ALL_IDS,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unwritable_event_table_when_migrating_then_promotion_rolls_back(
    tmp_path: Path,
    test_case: PostgresMigrationRollbackE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    """Promotion and the migration event commit or roll back together on PostgreSQL."""

    schema_name: str = build_unique_schema_name(prefix="sqlbuild_migration_rollback")
    raw_schema_name: str = f"{schema_name}_raw"
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    load_raw_orders(raw_schema_name=raw_schema_name, config=postgres_e2e_config)
    project_dir: Path = write_migration_project(
        tmp_path=tmp_path,
        schema_name=schema_name,
        raw_schema_name=raw_schema_name,
        config=postgres_e2e_config,
        models={
            ORIGIN_MODEL: orders_sql(),
            DESTINATION_MODEL: orders_sql(where=_TWO_ORDERS),
        },
    )
    try:
        initial: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        create_unwritable_migration_table(schema_name=schema_name, config=postgres_e2e_config)
        project_dir = write_migration_project(
            tmp_path=tmp_path,
            schema_name=schema_name,
            raw_schema_name=raw_schema_name,
            config=postgres_e2e_config,
            models={DESTINATION_MODEL: orders_sql(migrate_from=ORIGIN_MODEL)},
        )
        failed: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        ids_after_failure: tuple[tuple[object, ...], ...] = ordered_ids(
            relation=f"{schema_name}.{DESTINATION_MODEL}", config=postgres_e2e_config
        )
        previous_after_failure: int = len(
            archive_names(
                schema_name=schema_name, kind="migration_previous", config=postgres_e2e_config
            )
        )
        execute_postgres_sql(
            sql=f"DROP VIEW {schema_name}._sqlbuild_migrations", config=postgres_e2e_config
        )
        retried: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )

        assert initial.returncode == 0, initial.stdout + initial.stderr
        assert failed.returncode != 0
        assert test_case.expected_failure_fragment in failed.stdout + failed.stderr
        assert ids_after_failure == test_case.expected_destination_ids_after_failure
        assert previous_after_failure == test_case.expected_previous_archives_after_failure
        assert retried.returncode == 0, retried.stdout + retried.stderr
        assert (
            ordered_ids(relation=f"{schema_name}.{DESTINATION_MODEL}", config=postgres_e2e_config)
            == test_case.expected_final_destination_ids
        )
    finally:
        cleanup_postgres_schema(schema_name=raw_schema_name, config=postgres_e2e_config)
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
