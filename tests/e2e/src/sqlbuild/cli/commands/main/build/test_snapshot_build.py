"""E2E tests for snapshot build behavior."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    SnapshotCheckBuildE2ETestCase,
    SnapshotCheckFailureBuildE2ETestCase,
    SnapshotFullRefreshFailureBuildE2ETestCase,
    SnapshotFullRefreshSuccessBuildE2ETestCase,
    SnapshotHistoricalCheckBuildE2ETestCase,
    SnapshotHistoricalTimestampBuildE2ETestCase,
    SnapshotTimestampBuildE2ETestCase,
    SnapshotTimestampFailureBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)

SNAPSHOT_TIMESTAMP_TEST_CASES: list[SnapshotTimestampBuildE2ETestCase] = [
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
                      updated_at updated_at,
                      valid_from_column effective_from,
                      valid_to_column effective_to
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
            "SELECT customer_id, plan, CAST(effective_from AS VARCHAR), "
            "CAST(effective_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, effective_from"
        ),
        expected_initial_rows=((1, "basic", "2024-01-01 00:00:00", None),),
        expected_changed_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
            (1, "pro", "2024-01-03 00:00:00", None),
            (2, "basic", "2024-01-02 00:00:00", None),
        ),
    ),
    SnapshotTimestampBuildE2ETestCase(
        description="current-state timestamp snapshot invalidates hard deletes through CLI",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                    name = "snapshot_project"
                    adapter = "duckdb"

                    [connection]
                    database = "snapshot.duckdb"
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
                      updated_at updated_at,
                      invalidate_hard_deletes true
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
                SELECT 2 AS customer_id, 'pro' AS plan,
                  TIMESTAMP '2024-01-02 00:00:00' AS updated_at
                """
        ).strip(),
        mutation_sql=(
            dedent(
                """
                    CREATE OR REPLACE TABLE main.raw_customers AS
                    SELECT 1 AS customer_id, 'basic' AS plan,
                      TIMESTAMP '2024-01-01 00:00:00' AS updated_at
                    """
            ).strip(),
        ),
        command=("--no-color", "build"),
        expected_exit_code=0,
        expected_query=(
            "SELECT customer_id, plan, valid_to IS NULL FROM main.customer_snapshot "
            "ORDER BY customer_id"
        ),
        expected_initial_rows=((1, "basic", True), (2, "pro", True)),
        expected_changed_rows=((1, "basic", True), (2, "pro", False)),
    ),
]

SNAPSHOT_CHECK_TEST_CASES: list[SnapshotCheckBuildE2ETestCase] = [
    SnapshotCheckBuildE2ETestCase(
        description="current-state check snapshot tracks checked changes across CLI builds",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "check_snapshot_project"
                adapter = "duckdb"

                [connection]
                database = "check_snapshot.duckdb"
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
                  snapshot_strategy check,
                  check_columns [status],
                  valid_from_column effective_from,
                  valid_to_column effective_to
                );

                SELECT customer_id, plan, status
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
              status VARCHAR
            );

            INSERT INTO main.raw_customers VALUES
              (1, 'basic', 'active');
            """
        ).strip(),
        mutation_sql=(
            dedent(
                """
                CREATE OR REPLACE TABLE main.raw_customers AS
                SELECT 1 AS customer_id, 'pro' AS plan, 'paused' AS status
                UNION ALL
                SELECT 2 AS customer_id, 'basic' AS plan, 'active' AS status
                """
            ).strip(),
        ),
        command=("--no-color", "build"),
        expected_exit_code=0,
        expected_query=(
            "SELECT customer_id, plan, status, effective_to IS NULL "
            "FROM main.customer_snapshot ORDER BY customer_id, effective_to IS NULL, plan"
        ),
        expected_initial_rows=((1, "basic", "active", True),),
        expected_changed_rows=(
            (1, "basic", "active", False),
            (1, "pro", "paused", True),
            (2, "basic", "active", True),
        ),
    ),
    SnapshotCheckBuildE2ETestCase(
        description="current-state check snapshot invalidates hard deletes through CLI",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "check_snapshot_project"
                adapter = "duckdb"

                [connection]
                database = "check_snapshot.duckdb"
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
                  snapshot_strategy check,
                  check_columns [status],
                  invalidate_hard_deletes true
                );

                SELECT customer_id, plan, status
                FROM __source("raw_customers")
                """
            ).strip()
            + "\n",
        },
        initial_seed_sql=dedent(
            """
            CREATE TABLE main.raw_customers AS
            SELECT 1 AS customer_id, 'basic' AS plan, 'active' AS status
            UNION ALL
            SELECT 2 AS customer_id, 'pro' AS plan, 'active' AS status
            """
        ).strip(),
        mutation_sql=(
            dedent(
                """
                CREATE OR REPLACE TABLE main.raw_customers AS
                SELECT 1 AS customer_id, 'basic' AS plan, 'active' AS status
                """
            ).strip(),
        ),
        command=("--no-color", "build"),
        expected_exit_code=0,
        expected_query=(
            "SELECT customer_id, plan, status, valid_to IS NULL "
            "FROM main.customer_snapshot ORDER BY customer_id"
        ),
        expected_initial_rows=((1, "basic", "active", True), (2, "pro", "active", True)),
        expected_changed_rows=((1, "basic", "active", True), (2, "pro", "active", False)),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_TIMESTAMP_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_TIMESTAMP_TEST_CASES],
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


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_CHECK_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_CHECK_TEST_CASES],
)
def test_given_check_snapshot_project_when_rerunning_build_then_tracks_checked_changes(
    test_case: SnapshotCheckBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="check_snapshot_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "check_snapshot.duckdb"

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
        SnapshotHistoricalCheckBuildE2ETestCase(
            description="historical check snapshot tracks observed history through CLI",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                    name = "historical_check_snapshot_project"
                    adapter = "duckdb"

                    [connection]
                    database = "historical_check_snapshot.duckdb"
                    """
                ).strip()
                + "\n",
                "sources/raw.yml": dedent(
                    """
                    sources:
                      - name: raw_customer_daily
                        schema: main
                        table: raw_customer_daily
                    """
                ).strip()
                + "\n",
                "models/customer_snapshot.sql": dedent(
                    """
                    MODEL (
                      materialized snapshot,
                      unique_key [customer_id],
                      snapshot_strategy check,
                      check_columns [plan],
                      observed_at observed_at
                    );

                    SELECT customer_id, plan, observed_at
                    FROM __source("raw_customer_daily")
                    """
                ).strip()
                + "\n",
            },
            initial_seed_sql=dedent(
                """
                CREATE TABLE main.raw_customer_daily AS
                SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS observed_at
                UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-02'
                UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-03'
                UNION ALL SELECT 1, 'team', TIMESTAMP '2024-01-04'
                """
            ).strip(),
            mutation_sql=(
                dedent(
                    """
                    CREATE OR REPLACE TABLE main.raw_customer_daily AS
                    SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS observed_at
                    UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-02'
                    UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-03'
                    UNION ALL SELECT 1, 'team', TIMESTAMP '2024-01-04'
                    UNION ALL SELECT 1, 'enterprise', TIMESTAMP '2024-01-05'
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
            expected_initial_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-02 00:00:00"),
                (1, "pro", "2024-01-02 00:00:00", "2024-01-04 00:00:00"),
                (1, "team", "2024-01-04 00:00:00", None),
            ),
            expected_changed_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-02 00:00:00"),
                (1, "pro", "2024-01-02 00:00:00", "2024-01-04 00:00:00"),
                (1, "team", "2024-01-04 00:00:00", "2024-01-05 00:00:00"),
                (1, "enterprise", "2024-01-05 00:00:00", None),
            ),
        )
    ],
    ids=["historical check snapshot tracks observed history through CLI"],
)
def test_given_historical_check_snapshot_project_when_rerunning_build_then_tracks_history(
    test_case: SnapshotHistoricalCheckBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="historical_check_snapshot_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "historical_check_snapshot.duckdb"

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

    connection = duckdb.connect(str(db_path))
    statement: str
    for statement in test_case.mutation_sql:
        connection.execute(statement)
    connection.close()

    second_result: object = run_sqb(command=test_case.command, project_dir=project_dir)
    assert second_result.returncode == test_case.expected_exit_code, (
        second_result.stdout + second_result.stderr
    )
    rows_after_changed: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in query_duckdb(db_path=db_path, sql=test_case.expected_query)
    )

    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_changed == test_case.expected_changed_rows


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotHistoricalTimestampBuildE2ETestCase(
            description="historical timestamp snapshot tracks updated history through CLI",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                    name = "historical_timestamp_snapshot_project"
                    adapter = "duckdb"

                    [connection]
                    database = "historical_timestamp_snapshot.duckdb"
                    """
                ).strip()
                + "\n",
                "sources/raw.yml": dedent(
                    """
                    sources:
                      - name: raw_customer_extracts
                        schema: main
                        table: raw_customer_extracts
                    """
                ).strip()
                + "\n",
                "models/customer_snapshot.sql": dedent(
                    """
                    MODEL (
                      materialized snapshot,
                      unique_key [customer_id],
                      snapshot_strategy timestamp,
                      updated_at updated_at,
                      observed_at observed_at,
                      historical_input snapshot
                    );

                    SELECT customer_id, plan, updated_at, observed_at
                    FROM __source("raw_customer_extracts")
                    """
                ).strip()
                + "\n",
            },
            initial_seed_sql=dedent(
                """
                CREATE TABLE main.raw_customer_extracts AS
                SELECT 1 AS customer_id, 'basic' AS plan,
                  TIMESTAMP '2024-01-01' AS updated_at,
                  TIMESTAMP '2024-01-02' AS observed_at
                UNION ALL SELECT 1, 'basic', TIMESTAMP '2024-01-01', TIMESTAMP '2024-01-03'
                UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-04', TIMESTAMP '2024-01-06'
                """
            ).strip(),
            mutation_sql=(
                dedent(
                    """
                    CREATE OR REPLACE TABLE main.raw_customer_extracts AS
                    SELECT 1 AS customer_id, 'basic' AS plan,
                      TIMESTAMP '2024-01-01' AS updated_at,
                      TIMESTAMP '2024-01-02' AS observed_at
                    UNION ALL SELECT 1, 'basic', TIMESTAMP '2024-01-01', TIMESTAMP '2024-01-03'
                    UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-04', TIMESTAMP '2024-01-06'
                    UNION ALL SELECT 1, 'team', TIMESTAMP '2024-01-07', TIMESTAMP '2024-01-08'
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
            expected_initial_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
                (1, "pro", "2024-01-04 00:00:00", None),
            ),
            expected_changed_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
                (1, "pro", "2024-01-04 00:00:00", "2024-01-07 00:00:00"),
                (1, "team", "2024-01-07 00:00:00", None),
            ),
        )
    ],
    ids=["historical timestamp snapshot tracks updated history through CLI"],
)
def test_given_historical_timestamp_snapshot_project_when_rerunning_build_then_tracks_history(
    test_case: SnapshotHistoricalTimestampBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="historical_timestamp_snapshot_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "historical_timestamp_snapshot.duckdb"

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

    connection = duckdb.connect(str(db_path))
    statement: str
    for statement in test_case.mutation_sql:
        connection.execute(statement)
    connection.close()

    second_result: object = run_sqb(command=test_case.command, project_dir=project_dir)
    assert second_result.returncode == test_case.expected_exit_code, (
        second_result.stdout + second_result.stderr
    )
    rows_after_changed: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in query_duckdb(db_path=db_path, sql=test_case.expected_query)
    )

    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_changed == test_case.expected_changed_rows


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotCheckFailureBuildE2ETestCase(
            description="missing check snapshot output column fails build through CLI",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                    name = "check_snapshot_failure_project"
                    adapter = "duckdb"

                    [connection]
                    database = "check_snapshot_failure.duckdb"
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
                      snapshot_strategy check,
                      check_columns [status]
                    );

                    SELECT customer_id, plan
                    FROM __source("raw_customers")
                    """
                ).strip()
                + "\n",
            },
            initial_seed_sql=dedent(
                """
                CREATE TABLE main.raw_customers AS
                SELECT 1 AS customer_id, 'basic' AS plan, 'active' AS status
                """
            ).strip(),
            command=("--no-color", "build"),
            expected_exit_code=1,
            expected_output_fragments=(
                "customer_snapshot",
                "query output is missing required columns: status",
            ),
        )
    ],
    ids=["missing check snapshot output column fails build through CLI"],
)
def test_given_missing_check_snapshot_output_column_when_building_then_cli_reports_failure(
    test_case: SnapshotCheckFailureBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="check_snapshot_failure_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "check_snapshot_failure.duckdb"

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


SNAPSHOT_FULL_REFRESH_FAILURE_TEST_CASES: list[SnapshotFullRefreshFailureBuildE2ETestCase] = [
    SnapshotFullRefreshFailureBuildE2ETestCase(
        description="current-state snapshot full refresh is denied by default through CLI",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                    name = "snapshot_full_refresh_project"
                    adapter = "duckdb"

                    [connection]
                    database = "snapshot_full_refresh.duckdb"
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
                """
        ).strip(),
        initial_command=("--no-color", "build"),
        full_refresh_command=("--no-color", "build", "--full-refresh"),
        expected_exit_code=1,
        expected_output_fragments=(
            "full refresh is denied for snapshot model 'customer_snapshot'",
            "snapshot_full_refresh policy",
        ),
    ),
    SnapshotFullRefreshFailureBuildE2ETestCase(
        description="current-state snapshot full refresh is denied by default through run CLI",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                    name = "snapshot_full_refresh_project"
                    adapter = "duckdb"

                    [connection]
                    database = "snapshot_full_refresh.duckdb"
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
                """
        ).strip(),
        initial_command=("--no-color", "build"),
        full_refresh_command=("--no-color", "run", "--full-refresh"),
        expected_exit_code=1,
        expected_output_fragments=(
            "full refresh is denied for snapshot model 'customer_snapshot'",
            "snapshot_full_refresh policy",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_FULL_REFRESH_FAILURE_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_FULL_REFRESH_FAILURE_TEST_CASES],
)
def test_given_snapshot_full_refresh_default_deny_when_building_then_cli_reports_failure(
    test_case: SnapshotFullRefreshFailureBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="snapshot_full_refresh_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "snapshot_full_refresh.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute(test_case.initial_seed_sql)
    connection.close()

    initial_result: object = run_sqb(command=test_case.initial_command, project_dir=project_dir)
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

    result: object = run_sqb(command=test_case.full_refresh_command, project_dir=project_dir)

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    output: str = result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output


SNAPSHOT_FULL_REFRESH_SUCCESS_TEST_CASES: list[SnapshotFullRefreshSuccessBuildE2ETestCase] = [
    SnapshotFullRefreshSuccessBuildE2ETestCase(
        description="current-state timestamp snapshot full refresh rebuilds when allowed",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                    name = "historical_snapshot_full_refresh_project"
                    adapter = "duckdb"

                    [connection]
                    database = "historical_snapshot_full_refresh.duckdb"

                    [snapshots]
                    current_state_full_refresh = "allow"
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
                SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS updated_at
                """
        ).strip(),
        mutation_sql=(
            dedent(
                """
                    CREATE OR REPLACE TABLE main.raw_customers AS
                    SELECT 1 AS customer_id, 'team' AS plan, TIMESTAMP '2024-02-01' AS updated_at
                    """
            ).strip(),
        ),
        initial_command=("--no-color", "build"),
        full_refresh_command=("--no-color", "build", "--full-refresh"),
        expected_exit_code=0,
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=((1, "basic", "2024-01-01 00:00:00", None),),
        expected_refreshed_rows=((1, "team", "2024-02-01 00:00:00", None),),
    ),
    SnapshotFullRefreshSuccessBuildE2ETestCase(
        description="current-state check snapshot full refresh rebuilds when allowed",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                    name = "historical_snapshot_full_refresh_project"
                    adapter = "duckdb"

                    [connection]
                    database = "historical_snapshot_full_refresh.duckdb"

                    [snapshots]
                    current_state_full_refresh = "allow"
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
                      snapshot_strategy check,
                      check_columns [plan]
                    );

                    SELECT customer_id, plan
                    FROM __source("raw_customers")
                    """
            ).strip()
            + "\n",
        },
        initial_seed_sql=dedent(
            """
                CREATE TABLE main.raw_customers AS
                SELECT 1 AS customer_id, 'basic' AS plan
                """
        ).strip(),
        mutation_sql=(
            dedent(
                """
                    CREATE OR REPLACE TABLE main.raw_customers AS
                    SELECT 1 AS customer_id, 'team' AS plan
                    """
            ).strip(),
        ),
        initial_command=("--no-color", "build"),
        full_refresh_command=("--no-color", "build", "--full-refresh"),
        expected_exit_code=0,
        expected_query=(
            "SELECT customer_id, plan, valid_to FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=((1, "basic", None),),
        expected_refreshed_rows=((1, "team", None),),
    ),
    SnapshotFullRefreshSuccessBuildE2ETestCase(
        description="historical check snapshot full refresh runs with confirmation flag",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                    name = "historical_snapshot_full_refresh_project"
                    adapter = "duckdb"

                    [connection]
                    database = "historical_snapshot_full_refresh.duckdb"
                    """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                    sources:
                      - name: raw_customer_daily
                        schema: main
                        table: raw_customer_daily
                    """
            ).strip()
            + "\n",
            "models/customer_snapshot.sql": dedent(
                """
                    MODEL (
                      materialized snapshot,
                      unique_key [customer_id],
                      snapshot_strategy check,
                      check_columns [plan],
                      observed_at observed_at
                    );

                    SELECT customer_id, plan, observed_at
                    FROM __source("raw_customer_daily")
                    """
            ).strip()
            + "\n",
        },
        initial_seed_sql=dedent(
            """
                CREATE TABLE main.raw_customer_daily AS
                SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS observed_at
                UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-02'
                """
        ).strip(),
        mutation_sql=(
            dedent(
                """
                    CREATE OR REPLACE TABLE main.raw_customer_daily AS
                    SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-02-01' AS observed_at
                    UNION ALL SELECT 1, 'team', TIMESTAMP '2024-02-03'
                    """
            ).strip(),
        ),
        initial_command=("--no-color", "build"),
        full_refresh_command=(
            "--no-color",
            "build",
            "--full-refresh",
            "--allow-snapshot-full-refresh",
        ),
        expected_exit_code=0,
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-02 00:00:00"),
            (1, "pro", "2024-01-02 00:00:00", None),
        ),
        expected_refreshed_rows=(
            (1, "basic", "2024-02-01 00:00:00", "2024-02-03 00:00:00"),
            (1, "team", "2024-02-03 00:00:00", None),
        ),
    ),
    SnapshotFullRefreshSuccessBuildE2ETestCase(
        description="historical check snapshot full refresh rebuilds through run command",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                    name = "historical_snapshot_full_refresh_project"
                    adapter = "duckdb"

                    [connection]
                    database = "historical_snapshot_full_refresh.duckdb"
                    """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                    sources:
                      - name: raw_customer_daily
                        schema: main
                        table: raw_customer_daily
                    """
            ).strip()
            + "\n",
            "models/customer_snapshot.sql": dedent(
                """
                    MODEL (
                      materialized snapshot,
                      unique_key [customer_id],
                      snapshot_strategy check,
                      check_columns [plan],
                      observed_at observed_at
                    );

                    SELECT customer_id, plan, observed_at
                    FROM __source("raw_customer_daily")
                    """
            ).strip()
            + "\n",
        },
        initial_seed_sql=dedent(
            """
                CREATE TABLE main.raw_customer_daily AS
                SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS observed_at
                UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-02'
                """
        ).strip(),
        mutation_sql=(
            dedent(
                """
                    CREATE OR REPLACE TABLE main.raw_customer_daily AS
                    SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-02-01' AS observed_at
                    UNION ALL SELECT 1, 'team', TIMESTAMP '2024-02-03'
                    """
            ).strip(),
        ),
        initial_command=("--no-color", "build"),
        full_refresh_command=(
            "--no-color",
            "run",
            "--full-refresh",
            "--allow-snapshot-full-refresh",
        ),
        expected_exit_code=0,
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-02 00:00:00"),
            (1, "pro", "2024-01-02 00:00:00", None),
        ),
        expected_refreshed_rows=(
            (1, "basic", "2024-02-01 00:00:00", "2024-02-03 00:00:00"),
            (1, "team", "2024-02-03 00:00:00", None),
        ),
    ),
    SnapshotFullRefreshSuccessBuildE2ETestCase(
        description="historical timestamp snapshot full refresh rebuilds through build command",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                    name = "historical_snapshot_full_refresh_project"
                    adapter = "duckdb"

                    [connection]
                    database = "historical_snapshot_full_refresh.duckdb"
                    """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                    sources:
                      - name: raw_customer_extracts
                        schema: main
                        table: raw_customer_extracts
                    """
            ).strip()
            + "\n",
            "models/customer_snapshot.sql": dedent(
                """
                    MODEL (
                      materialized snapshot,
                      unique_key [customer_id],
                      snapshot_strategy timestamp,
                      updated_at updated_at,
                      observed_at observed_at,
                      historical_input snapshot
                    );

                    SELECT customer_id, plan, updated_at, observed_at
                    FROM __source("raw_customer_extracts")
                    """
            ).strip()
            + "\n",
        },
        initial_seed_sql=dedent(
            """
                CREATE TABLE main.raw_customer_extracts AS
                SELECT 1 AS customer_id, 'basic' AS plan,
                  TIMESTAMP '2024-01-01' AS updated_at,
                  TIMESTAMP '2024-01-02' AS observed_at
                UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-04', TIMESTAMP '2024-01-06'
                """
        ).strip(),
        mutation_sql=(
            dedent(
                """
                    CREATE OR REPLACE TABLE main.raw_customer_extracts AS
                    SELECT 1 AS customer_id, 'basic' AS plan,
                      TIMESTAMP '2024-02-01' AS updated_at,
                      TIMESTAMP '2024-02-02' AS observed_at
                    UNION ALL SELECT 1, 'team', TIMESTAMP '2024-02-04', TIMESTAMP '2024-02-06'
                    """
            ).strip(),
        ),
        initial_command=("--no-color", "build"),
        full_refresh_command=(
            "--no-color",
            "build",
            "--full-refresh",
            "--allow-snapshot-full-refresh",
        ),
        expected_exit_code=0,
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
            (1, "pro", "2024-01-04 00:00:00", None),
        ),
        expected_refreshed_rows=(
            (1, "basic", "2024-02-01 00:00:00", "2024-02-04 00:00:00"),
            (1, "team", "2024-02-04 00:00:00", None),
        ),
    ),
    SnapshotFullRefreshSuccessBuildE2ETestCase(
        description="historical timestamp snapshot full refresh rebuilds through run command",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                    name = "historical_snapshot_full_refresh_project"
                    adapter = "duckdb"

                    [connection]
                    database = "historical_snapshot_full_refresh.duckdb"
                    """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                    sources:
                      - name: raw_customer_extracts
                        schema: main
                        table: raw_customer_extracts
                    """
            ).strip()
            + "\n",
            "models/customer_snapshot.sql": dedent(
                """
                    MODEL (
                      materialized snapshot,
                      unique_key [customer_id],
                      snapshot_strategy timestamp,
                      updated_at updated_at,
                      observed_at observed_at,
                      historical_input snapshot
                    );

                    SELECT customer_id, plan, updated_at, observed_at
                    FROM __source("raw_customer_extracts")
                    """
            ).strip()
            + "\n",
        },
        initial_seed_sql=dedent(
            """
                CREATE TABLE main.raw_customer_extracts AS
                SELECT 1 AS customer_id, 'basic' AS plan,
                  TIMESTAMP '2024-01-01' AS updated_at,
                  TIMESTAMP '2024-01-02' AS observed_at
                UNION ALL SELECT 1, 'pro', TIMESTAMP '2024-01-04', TIMESTAMP '2024-01-06'
                """
        ).strip(),
        mutation_sql=(
            dedent(
                """
                    CREATE OR REPLACE TABLE main.raw_customer_extracts AS
                    SELECT 1 AS customer_id, 'basic' AS plan,
                      TIMESTAMP '2024-02-01' AS updated_at,
                      TIMESTAMP '2024-02-02' AS observed_at
                    UNION ALL SELECT 1, 'team', TIMESTAMP '2024-02-04', TIMESTAMP '2024-02-06'
                    """
            ).strip(),
        ),
        initial_command=("--no-color", "build"),
        full_refresh_command=(
            "--no-color",
            "run",
            "--full-refresh",
            "--allow-snapshot-full-refresh",
        ),
        expected_exit_code=0,
        expected_query=(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), "
            "CAST(valid_to AS VARCHAR) FROM main.customer_snapshot "
            "ORDER BY customer_id, valid_from"
        ),
        expected_initial_rows=(
            (1, "basic", "2024-01-01 00:00:00", "2024-01-04 00:00:00"),
            (1, "pro", "2024-01-04 00:00:00", None),
        ),
        expected_refreshed_rows=(
            (1, "basic", "2024-02-01 00:00:00", "2024-02-04 00:00:00"),
            (1, "team", "2024-02-04 00:00:00", None),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_FULL_REFRESH_SUCCESS_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_FULL_REFRESH_SUCCESS_TEST_CASES],
)
def test_given_snapshot_full_refresh_allowed_when_building_then_rebuilds_history(
    test_case: SnapshotFullRefreshSuccessBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="historical_snapshot_full_refresh_project",
        repo_files=test_case.repo_files,
    )
    db_path: Path = project_dir / "historical_snapshot_full_refresh.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute(test_case.initial_seed_sql)
    connection.close()

    initial_result: object = run_sqb(command=test_case.initial_command, project_dir=project_dir)
    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr
    rows_after_initial: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in query_duckdb(db_path=db_path, sql=test_case.expected_query)
    )

    connection = duckdb.connect(str(db_path))
    statement: str
    for statement in test_case.mutation_sql:
        connection.execute(statement)
    connection.close()

    refresh_result: object = run_sqb(
        command=test_case.full_refresh_command, project_dir=project_dir
    )
    assert refresh_result.returncode == test_case.expected_exit_code, (
        refresh_result.stdout + refresh_result.stderr
    )
    rows_after_refresh: tuple[tuple[object, ...], ...] = tuple(
        tuple(row) for row in query_duckdb(db_path=db_path, sql=test_case.expected_query)
    )

    assert rows_after_initial == test_case.expected_initial_rows
    assert rows_after_refresh == test_case.expected_refreshed_rows
