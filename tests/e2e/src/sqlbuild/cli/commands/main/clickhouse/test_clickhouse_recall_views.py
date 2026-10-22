from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse._test_types import (
    ClickHouseRecallPreviousVersionTestCase,
    ClickHouseRecallTableReadsTestCase,
    ClickHouseRecallViewEquivalenceTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import (
    create_previous_views,
    described,
    differing_rows,
    execute_clickhouse_sql,
    fetch_clickhouse_rows,
    limited_user,
    primary_key_reads,
    representative_store,
    table_reads,
    write_recall_project,
)
from tests.integration.src.sqlbuild.cli.recall.helpers import recall_rows, run


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallViewEquivalenceTestCase(
            description="rewritten views match the previous ones",
            replaced_views=("invocations", "statements"),
            all_views=(),
            expected_statuses=[
                ["abandoned"],
                ["abandoned"],
                ["completed"],
                ["failed"],
                ["running"],
            ],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_representative_invocations_when_views_are_rewritten_then_rows_and_types_are_unchanged(
    test_case: ClickHouseRecallViewEquivalenceTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    running: subprocess.Popen[bytes] = representative_store(project_dir)
    try:
        create_previous_views(
            config=clickhouse_e2e_config,
            database=recall_database,
            names=test_case.replaced_views,
            prefix="previous_",
        )
        statuses: list[list[object]] = recall_rows(
            project_dir, "SELECT status FROM invocations ORDER BY status"
        )
        against_previous: list[int] = [
            differing_rows(
                config=clickhouse_e2e_config,
                left=f"{recall_database}.{view}",
                right=f"{recall_database}.previous_{view}",
                settings={"join_use_nulls": 1},
            )
            for view in test_case.replaced_views
        ]
        types: list[bool] = [
            described(config=clickhouse_e2e_config, relation=f"{recall_database}.{view}")
            == described(
                config=clickhouse_e2e_config, relation=f"{recall_database}.previous_{view}"
            )
            for view in test_case.replaced_views
        ]
    finally:
        os.killpg(running.pid, signal.SIGKILL)
        _ = running.wait(timeout=30)

    assert statuses == test_case.expected_statuses
    assert against_previous == [0 for _ in test_case.replaced_views]
    assert types == [True for _ in test_case.replaced_views]


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallTableReadsTestCase(
            description="invocations reads its three tables once each",
            view="invocations",
            expected_tables=("recall_events", "recall_heartbeats", "recall_invocations"),
            expected_primary_key_reads=3,
        ),
        ClickHouseRecallTableReadsTestCase(
            description="statements reads the events once and the stored SQL once",
            view="statements",
            expected_tables=("recall_artifacts", "recall_events"),
            expected_primary_key_reads=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_one_invocation_lookup_when_planned_then_each_table_is_read_once_by_its_key(
    test_case: ClickHouseRecallTableReadsTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    assert run(project_dir, "build").returncode == 0
    sql: str = (
        f"SELECT * FROM {recall_database}.{test_case.view} WHERE invocation_id = 'any-invocation'"
    )

    reads: tuple[str, ...] = table_reads(config=clickhouse_e2e_config, sql=sql)
    keyed: int = primary_key_reads(config=clickhouse_e2e_config, sql=sql)

    assert reads == tuple(f"{recall_database}.{table}" for table in test_case.expected_tables)
    assert keyed == test_case.expected_primary_key_reads


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallPreviousVersionTestCase(
            description="a store of the previous version is upgraded by whoever may",
            replaced_views=("invocations", "statements"),
            expected_notice="is behind this SQLBuild version, and this user may not upgrade it",
            expected_ddl_fragments=(
                "CREATE OR REPLACE VIEW `{database}`.`invocations`",
                "CREATE OR REPLACE VIEW `{database}`.`statements`",
                "SELECT 'schema', 'schema_version', '3'",
            ),
            expected_version=((3,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_previous_version_store_when_built_then_limited_writers_warn_and_admins_upgrade(
    test_case: ClickHouseRecallPreviousVersionTestCase,
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
        names=test_case.replaced_views,
        prefix="",
    )
    execute_clickhouse_sql(
        config=clickhouse_e2e_config,
        statements=(
            f"ALTER TABLE {recall_database}.recall_meta UPDATE value = '2' "
            "WHERE component = 'schema' SETTINGS mutations_sync = 2",
        ),
    )

    with limited_user(config=clickhouse_e2e_config, database=recall_database) as writer:
        writer_dir: Path = write_recall_project(
            parent=tmp_path / "writer", config=writer, database=recall_database
        )
        limited: subprocess.CompletedProcess[bytes] = run(writer_dir, "build")
        printed: subprocess.CompletedProcess[bytes] = run(writer_dir, "recall", "schema", "--ddl")
    upgraded: subprocess.CompletedProcess[bytes] = run(admin, "build")
    repeated: subprocess.CompletedProcess[bytes] = run(admin, "recall", "schema", "--ddl")

    ddl: str = printed.stdout.decode()
    assert limited.returncode == 0, limited.stderr
    assert test_case.expected_notice in limited.stderr.decode(errors="replace")
    assert [
        fragment.format(database=recall_database) in ddl
        for fragment in test_case.expected_ddl_fragments
    ] == [True for _ in test_case.expected_ddl_fragments]
    assert upgraded.returncode == 0, upgraded.stderr
    assert b"Recall" not in upgraded.stderr
    assert (repeated.returncode, repeated.stdout) == (0, b"")
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT max(toInt64OrZero(value)) FROM {recall_database}.recall_meta "
            "WHERE component = 'schema'",
        )
        == test_case.expected_version
    )
    assert recall_rows(admin, "SELECT count() FROM invocations") == [[3]]


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
