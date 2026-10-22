from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse._test_types import (
    ClickHouseRecallDatabaseCreationTestCase,
    ClickHouseRecallDocumentedGrantsTestCase,
    ClickHouseRecallExistingDatabaseTestCase,
    ClickHouseRecallExternalContextTestCase,
    ClickHouseRecallMissingDatabaseTestCase,
    ClickHouseRecallRefusedTablesTestCase,
    ClickHouseRecallStaleViewsTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import (
    apply_printed_ddl,
    create_previous_views,
    drop_database,
    execute_clickhouse_sql,
    fetch_clickhouse_rows,
    limited_user,
    stale_views,
    write_recall_project,
)
from tests.integration.src.sqlbuild.cli.recall.helpers import recall_rows, run

_STORE_MANAGER_PRIVILEGES: str = (
    "CREATE DATABASE, CREATE TABLE, CREATE VIEW, DROP TABLE, ALTER ADD COLUMN, SELECT, INSERT"
)
_CLOSING_STATUS: str = "sqb build completed successfully; only its Recall history is affected.\n"
_SUCCESS_STATUS: str = "sqb build completed successfully.\n"


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallDatabaseCreationTestCase(
            description="a writer with every right on the database creates it and says so",
            writer_privileges="ALL",
            expected_notice="Recall: created ClickHouse database `{database}` for the store.\n",
            expected_invocations=[[2]],
        ),
        ClickHouseRecallDatabaseCreationTestCase(
            description="a writer granted the documented store rights creates it too",
            writer_privileges=_STORE_MANAGER_PRIVILEGES,
            expected_notice="Recall: created ClickHouse database `{database}` for the store.\n",
            expected_invocations=[[2]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_missing_database_when_a_writer_may_create_it_then_recall_creates_the_store(
    test_case: ClickHouseRecallDatabaseCreationTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    drop_database(config=clickhouse_e2e_config, database=recall_database)
    notice: str = test_case.expected_notice.format(database=recall_database)

    with limited_user(
        config=clickhouse_e2e_config,
        database=recall_database,
        privileges=test_case.writer_privileges,
    ) as writer:
        project_dir: Path = write_recall_project(
            parent=tmp_path, config=writer, database=recall_database
        )
        first: subprocess.CompletedProcess[bytes] = run(project_dir, "build")
        second: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    stderr: str = first.stderr.decode(errors="replace")
    assert (first.returncode, second.returncode) == (0, 0), stderr
    assert stderr.count(notice) == 1
    assert stderr.endswith(notice + _SUCCESS_STATUS)
    assert b"Recall" not in second.stderr
    assert (
        recall_rows(
            write_recall_project(
                parent=tmp_path / "admin", config=clickhouse_e2e_config, database=recall_database
            ),
            "SELECT count() FROM invocations WHERE command = 'build'",
        )
        == test_case.expected_invocations
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallExistingDatabaseTestCase(
            description="an existing database is used without any CREATE DATABASE",
            expected_database_creations=((0,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_an_existing_database_when_building_then_recall_leaves_the_database_alone(
    test_case: ClickHouseRecallExistingDatabaseTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )

    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    execute_clickhouse_sql(config=clickhouse_e2e_config, statements=("SYSTEM FLUSH LOGS",))
    assert built.returncode == 0, built.stderr
    assert b"Recall" not in built.stderr
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql="SELECT count() FROM system.query_log WHERE type = 'QueryStart' "
            f"AND query ILIKE 'CREATE DATABASE IF NOT EXISTS%{recall_database}%'",
        )
        == test_case.expected_database_creations
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallMissingDatabaseTestCase(
            description="a SELECT, INSERT writer gets the exact statements, then writes once run",
            writer_privileges="SELECT, INSERT",
            expected_fragments=(
                "Recall history is not being written for target `dev`: ClickHouse database "
                "`{database}` does not exist, and this user may not create it",
                "with:\n\nCREATE DATABASE IF NOT EXISTS `{database}`;\n\n"
                "CREATE TABLE IF NOT EXISTS `{database}`.`recall_meta`",
                "CREATE OR REPLACE VIEW `{database}`.`invocations`",
                _CLOSING_STATUS,
            ),
            expected_databases=((0,),),
            expected_invocations=[[1]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_missing_database_when_the_writer_may_not_create_it_then_the_statement_is_printed(
    test_case: ClickHouseRecallMissingDatabaseTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    drop_database(config=clickhouse_e2e_config, database=recall_database)

    with limited_user(
        config=clickhouse_e2e_config,
        database=recall_database,
        privileges=test_case.writer_privileges,
    ) as writer:
        project_dir: Path = write_recall_project(
            parent=tmp_path, config=writer, database=recall_database
        )
        refused: subprocess.CompletedProcess[bytes] = run(project_dir, "build")
        printed: subprocess.CompletedProcess[bytes] = run(project_dir, "recall", "schema", "--ddl")
        databases: tuple[tuple[object, ...], ...] = fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT count() FROM system.databases WHERE name = '{recall_database}'",
        )
        apply_printed_ddl(
            config=clickhouse_e2e_config, stderr=refused.stderr.decode(errors="replace")
        )
        written: subprocess.CompletedProcess[bytes] = run(project_dir, "build")
        invocations: list[list[object]] = recall_rows(
            project_dir, "SELECT count() FROM invocations WHERE command = 'build'"
        )

    stderr: str = refused.stderr.decode(errors="replace")
    assert refused.returncode == 0, stderr
    assert [
        fragment.format(database=recall_database) in stderr
        for fragment in test_case.expected_fragments
    ] == [True for _ in test_case.expected_fragments]
    assert printed.returncode == 0, printed.stderr
    assert printed.stdout.decode().startswith(
        f"CREATE DATABASE IF NOT EXISTS `{recall_database}`;\n"
    )
    assert databases == test_case.expected_databases
    assert written.returncode == 0, written.stderr
    assert b"Recall" not in written.stderr
    assert invocations == test_case.expected_invocations


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallStaleViewsTestCase(
            description="previous views without a version row are replaced by an administrator",
            deleted_version_rows="1",
            writer_privileges="ALL",
            expected_notices=0,
            expected_stale_views=((0,),),
            expected_version=((3,),),
        ),
        ClickHouseRecallStaleViewsTestCase(
            description="previous views recorded as current are replaced by an administrator",
            deleted_version_rows="0",
            writer_privileges="ALL",
            expected_notices=0,
            expected_stale_views=((0,),),
            expected_version=((3,),),
        ),
        ClickHouseRecallStaleViewsTestCase(
            description="previous views without a version row make a SELECT, INSERT writer warn",
            deleted_version_rows="1",
            writer_privileges="SELECT, INSERT",
            expected_notices=1,
            expected_stale_views=((4,),),
            expected_version=((0,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_views_of_the_previous_version_when_building_then_they_count_as_older(
    test_case: ClickHouseRecallStaleViewsTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    admin: Path = write_recall_project(
        parent=tmp_path / "admin", config=clickhouse_e2e_config, database=recall_database
    )
    assert run(admin, "build").returncode == 0
    create_previous_views(
        config=clickhouse_e2e_config,
        database=recall_database,
        names=("invocations", "statements", "output_invocations", "artifacts"),
        prefix="",
    )
    execute_clickhouse_sql(
        config=clickhouse_e2e_config,
        statements=(
            f"ALTER TABLE {recall_database}.recall_meta "
            f"DELETE WHERE {test_case.deleted_version_rows} SETTINGS mutations_sync = 2",
        ),
    )

    with limited_user(
        config=clickhouse_e2e_config,
        database=recall_database,
        privileges=test_case.writer_privileges,
    ) as writer:
        built: subprocess.CompletedProcess[bytes] = run(
            write_recall_project(
                parent=tmp_path / "writer", config=writer, database=recall_database
            ),
            "build",
        )

    stderr: str = built.stderr.decode(errors="replace")
    assert built.returncode == 0, stderr
    assert (
        stderr.count("is behind this SQLBuild version, and this user may not upgrade it")
        == test_case.expected_notices
    )
    assert stale_views(config=clickhouse_e2e_config, database=recall_database) == (
        test_case.expected_stale_views
    )
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT toInt64(max(toInt64OrZero(value))) FROM {recall_database}.recall_meta "
            "WHERE component = 'schema'",
        )
        == test_case.expected_version
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallExternalContextTestCase(
            description="an orchestrated job's runs are found with the documented JSON spelling",
            external_context='{"integration": {"name": "dagster", "job_name": "daily_models"}}',
            sql="SELECT status FROM invocations "
            "WHERE JSONExtractString(external_context, 'integration', 'job_name') = 'daily_models'",
            expected_rows=[["completed"]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_an_orchestrated_build_when_queried_on_clickhouse_then_its_context_is_json(
    test_case: ClickHouseRecallExternalContextTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )

    built: subprocess.CompletedProcess[bytes] = run(
        project_dir, "build", SQLBUILD_INVOCATION_CONTEXT_JSON=test_case.external_context
    )

    assert built.returncode == 0, built.stderr
    assert recall_rows(project_dir, test_case.sql) == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallRefusedTablesTestCase(
            description="a writer that may create the database but not tables still hears of it",
            writer_privileges="CREATE DATABASE, SELECT, INSERT",
            expected_fragments=(
                "Recall: created ClickHouse database `{database}` for the store.\n",
                "Recall history is not being written for target `dev`: cannot create the Recall "
                "tables",
                "CREATE TABLE IF NOT EXISTS `{database}`.`recall_meta`",
                _CLOSING_STATUS,
            ),
            expected_databases=((1,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_writer_that_may_create_only_the_database_when_building_then_both_are_reported(
    test_case: ClickHouseRecallRefusedTablesTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    drop_database(config=clickhouse_e2e_config, database=recall_database)

    with limited_user(
        config=clickhouse_e2e_config,
        database=recall_database,
        privileges=test_case.writer_privileges,
    ) as writer:
        built: subprocess.CompletedProcess[bytes] = run(
            write_recall_project(parent=tmp_path, config=writer, database=recall_database), "build"
        )

    stderr: str = built.stderr.decode(errors="replace")
    assert built.returncode == 0, stderr
    assert [
        stderr.count(fragment.format(database=recall_database))
        for fragment in test_case.expected_fragments
    ] == [1 for _ in test_case.expected_fragments]
    assert stderr.endswith(_CLOSING_STATUS)
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT count() FROM system.databases WHERE name = '{recall_database}'",
        )
        == test_case.expected_databases
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallDocumentedGrantsTestCase(
            description="the documented writer grants replace older views and add a column",
            writer_privileges=_STORE_MANAGER_PRIVILEGES,
            dropped_column=("recall_invocations", "argv_digest"),
            expected_columns=((1,),),
            expected_stale_views=((0,),),
            expected_version=((3,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_the_documented_writer_grants_when_the_store_is_behind_then_the_writer_upgrades_it(
    test_case: ClickHouseRecallDocumentedGrantsTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    table, column = test_case.dropped_column
    admin: Path = write_recall_project(
        parent=tmp_path / "admin", config=clickhouse_e2e_config, database=recall_database
    )
    assert run(admin, "build").returncode == 0
    create_previous_views(
        config=clickhouse_e2e_config,
        database=recall_database,
        names=("invocations", "statements", "output_invocations", "artifacts"),
        prefix="",
    )
    execute_clickhouse_sql(
        config=clickhouse_e2e_config,
        statements=(
            f"ALTER TABLE {recall_database}.{table} DROP COLUMN {column}",
            f"ALTER TABLE {recall_database}.recall_meta UPDATE value = '2' "
            "WHERE component = 'schema' SETTINGS mutations_sync = 2",
        ),
    )

    with limited_user(
        config=clickhouse_e2e_config,
        database=recall_database,
        privileges=test_case.writer_privileges,
    ) as writer:
        built: subprocess.CompletedProcess[bytes] = run(
            write_recall_project(
                parent=tmp_path / "writer", config=writer, database=recall_database
            ),
            "build",
        )

    assert built.returncode == 0, built.stderr
    assert b"Recall" not in built.stderr
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT count() FROM system.columns WHERE database = '{recall_database}' "
            f"AND table = '{table}' AND name = '{column}'",
        )
        == test_case.expected_columns
    )
    assert stale_views(config=clickhouse_e2e_config, database=recall_database) == (
        test_case.expected_stale_views
    )
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT toInt64(max(toInt64OrZero(value))) FROM {recall_database}.recall_meta "
            "WHERE component = 'schema'",
        )
        == test_case.expected_version
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
