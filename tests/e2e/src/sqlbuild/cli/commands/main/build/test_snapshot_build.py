"""E2E tests for snapshot build behavior."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    SnapshotTimestampBuildE2ETestCase,
    SnapshotTimestampFailureBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotTimestampBuildE2ETestCase(
            description="current-state timestamp snapshot tracks history across CLI builds",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                    name = "snapshot_project"
                    adapter = "duckdb"

                    [connection]
                    database = "snapshot.duckdb"

                    [defaults]
                    materialized = "table"
                    """
                ).strip()
                + "\n",
                "sources/raw.yml": dedent(
                    """
                    sources:
                      - name: raw_customers
                        schema: main
                        table: raw_customers
                    """
                ).strip()
                + "\n",
                "models/customer_snapshot.sql": dedent(
                    """
                    MODEL (
                      materialized snapshot,
                      unique_key [customer_id],
                      snapshot_strategy timestamp,
                      updated_at updated_at
                    );

                    SELECT customer_id, plan, updated_at
                    FROM __source("raw_customers")
                    """
                ).strip()
                + "\n",
            },
            initial_seed_sql=dedent(
                """
                CREATE TABLE main.raw_customers (
                  customer_id INTEGER,
                  plan VARCHAR,
                  updated_at TIMESTAMP
                );

                INSERT INTO main.raw_customers VALUES
                  (1, 'basic', '2024-01-01 00:00:00');
                """
            ).strip(),
            mutation_sql=(
                dedent(
                    """
                    CREATE OR REPLACE TABLE main.raw_customers AS
                    SELECT 1 AS customer_id, 'pro' AS plan,
                      TIMESTAMP '2024-01-03 00:00:00' AS updated_at
                    UNION ALL
                    SELECT 2 AS customer_id, 'basic' AS plan,
                      TIMESTAMP '2024-01-02 00:00:00' AS updated_at
                    """
                ).strip(),
            ),
            command=("--no-color", "build"),
            expected_exit_code=0,
            expected_query=(
                "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
                "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
                "ORDER BY customer_id, valid_from"
            ),
            expected_initial_rows=((1, "basic", "2024-01-01 00:00:00", None),),
            expected_changed_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
                (1, "pro", "2024-01-03 00:00:00", None),
                (2, "basic", "2024-01-02 00:00:00", None),
            ),
        )
    ],
    ids=["current-state timestamp snapshot tracks history across CLI builds"],
)
def test_given_timestamp_snapshot_project_when_rerunning_build_then_tracks_history(
    test_case: SnapshotTimestampBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="snapshot_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "snapshot.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute(test_case.initial_seed_sql)
    connection.close()

    first_result: object = run_sqb(command=test_case.command, project_dir=project_dir)
    assert first_result.returncode == test_case.expected_exit_code, (
        first_result.stdout + first_result.stderr
    )
    rows_after_initial: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in query_duckdb(db_path=db_path, sql=test_case.expected_query)
    )

    second_result: object = run_sqb(command=test_case.command, project_dir=project_dir)
    assert second_result.returncode == test_case.expected_exit_code, (
        second_result.stdout + second_result.stderr
    )
    rows_after_unchanged: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in query_duckdb(db_path=db_path, sql=test_case.expected_query)
    )

    connection = duckdb.connect(str(db_path))
    statement: str
    for statement in test_case.mutation_sql:
        connection.execute(statement)
    connection.close()

    third_result: object = run_sqb(command=test_case.command, project_dir=project_dir)
    assert third_result.returncode == test_case.expected_exit_code, (
        third_result.stdout + third_result.stderr
    )
    rows_after_changed: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in query_duckdb(db_path=db_path, sql=test_case.expected_query)
    )

    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_unchanged == test_case.expected_initial_rows
    assert rows_after_changed == test_case.expected_changed_rows


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotTimestampFailureBuildE2ETestCase(
            description="duplicate snapshot source key fails build through CLI",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                    name = "snapshot_failure_project"
                    adapter = "duckdb"

                    [connection]
                    database = "snapshot_failure.duckdb"
                    """
                ).strip()
                + "\n",
                "sources/raw.yml": dedent(
                    """
                    sources:
                      - name: raw_customers
                        schema: main
                        table: raw_customers
                    """
                ).strip()
                + "\n",
                "models/customer_snapshot.sql": dedent(
                    """
                    MODEL (
                      materialized snapshot,
                      unique_key [customer_id],
                      snapshot_strategy timestamp,
                      updated_at updated_at
                    );

                    SELECT customer_id, plan, updated_at
                    FROM __source("raw_customers")
                    """
                ).strip()
                + "\n",
            },
            initial_seed_sql=dedent(
                """
                CREATE TABLE main.raw_customers AS
                SELECT 1 AS customer_id, 'basic' AS plan,
                  TIMESTAMP '2024-01-01 00:00:00' AS updated_at
                UNION ALL
                SELECT 1 AS customer_id, 'pro' AS plan,
                  TIMESTAMP '2024-01-02 00:00:00' AS updated_at
                """
            ).strip(),
            command=("--no-color", "build"),
            expected_exit_code=1,
            expected_output_fragments=(
                "customer_snapshot",
                "source query returned multiple rows for the same unique_key (customer_id)",
            ),
        )
    ],
    ids=["duplicate snapshot source key fails build through CLI"],
)
def test_given_duplicate_timestamp_snapshot_source_when_building_then_cli_reports_failure(
    test_case: SnapshotTimestampFailureBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="snapshot_failure_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "snapshot_failure.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute(test_case.initial_seed_sql)
    connection.close()

    result: object = run_sqb(command=test_case.command, project_dir=project_dir)

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
