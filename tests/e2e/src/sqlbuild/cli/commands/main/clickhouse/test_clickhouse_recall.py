from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse._test_types import (
    ClickHouseRecallAbandonedTestCase,
    ClickHouseRecallConcurrencyTestCase,
    ClickHouseRecallDuplicateTestCase,
    ClickHouseRecallExpiryTestCase,
    ClickHouseRecallLimitedWriterTestCase,
    ClickHouseRecallOutputTestCase,
    ClickHouseRecallPermissionTestCase,
    ClickHouseRecallRetentionConflictTestCase,
    ClickHouseRecallRetentionTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import (
    age_recorded_invocations,
    apply_printed_ddl,
    apply_printed_retention_fix,
    duplicate_recall_rows,
    execute_clickhouse_sql,
    expire_recall_parts,
    fetch_clickhouse_rows,
    limited_user,
    physical_rows,
    stored_ttl_days,
    write_recall_project,
)
from tests.integration.src.sqlbuild.cli.recall.helpers import (
    concurrent_builds,
    killed_build,
    recall_rows,
    run,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallRetentionTestCase(
            description="the default keeps 30 days and artifacts a week longer",
            recall_settings="",
            expected_ttl_days=(
                ("recall_artifact_refs", 30),
                ("recall_artifacts", 37),
                ("recall_conflicts", 30),
                ("recall_delivery", 30),
                ("recall_diagnostics", 30),
                ("recall_events", 30),
                ("recall_heartbeats", 30),
                ("recall_invocations", 30),
                ("recall_meta", 30),
                ("recall_output", 30),
            ),
        ),
        ClickHouseRecallRetentionTestCase(
            description="a configured retention sets every table's TTL",
            recall_settings='retention = "7d"\n',
            expected_ttl_days=(
                ("recall_artifact_refs", 7),
                ("recall_artifacts", 14),
                ("recall_conflicts", 7),
                ("recall_delivery", 7),
                ("recall_diagnostics", 7),
                ("recall_events", 7),
                ("recall_heartbeats", 7),
                ("recall_invocations", 7),
                ("recall_meta", 7),
                ("recall_output", 7),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_retention_settings_when_building_then_recall_tables_expire_by_matching_ttls(
    test_case: ClickHouseRecallRetentionTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path,
        config=clickhouse_e2e_config,
        database=recall_database,
        settings=(test_case.recall_settings, ""),
    )

    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    assert built.returncode == 0, built.stderr
    assert b"Recall" not in built.stderr
    assert stored_ttl_days(config=clickhouse_e2e_config, database=recall_database) == (
        test_case.expected_ttl_days
    )
    assert recall_rows(project_dir, "SELECT status, exit_code FROM invocations") == [
        ["completed", 0]
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallExpiryTestCase(
            description="a shortened retention hides old runs at once and TTL drops them later",
            created_with="",
            recall_settings='retention = "7d"\n',
            aged_days=10,
            expected_fix_statements=20,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_rows_past_retention_when_queried_then_views_hide_them_before_ttl_drops_them(
    test_case: ClickHouseRecallExpiryTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    creator: Path = write_recall_project(
        parent=tmp_path / "creator",
        config=clickhouse_e2e_config,
        database=recall_database,
        settings=(test_case.created_with, ""),
    )
    assert run(creator, "build").returncode == 0
    age_recorded_invocations(
        config=clickhouse_e2e_config, database=recall_database, days=test_case.aged_days
    )
    project_dir: Path = write_recall_project(
        parent=tmp_path,
        config=clickhouse_e2e_config,
        database=recall_database,
        settings=(test_case.recall_settings, ""),
    )
    aged: str = "startsWith(invocation_id, 'aged-')"
    visible_sql: str = (
        f"SELECT (SELECT count() FROM invocations WHERE {aged}) "
        f"+ (SELECT count() FROM events WHERE {aged}) "
        f"+ (SELECT count() FROM output_transcripts WHERE {aged})"
    )
    visible_before: list[list[object]] = recall_rows(project_dir, visible_sql)
    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    applied: int = apply_printed_retention_fix(
        config=clickhouse_e2e_config, stderr=built.stderr.decode(errors="replace")
    )
    visible_after: list[list[object]] = recall_rows(project_dir, visible_sql)
    stored_before_ttl: int = physical_rows(
        config=clickhouse_e2e_config, database=recall_database, where=aged
    )
    expire_recall_parts(config=clickhouse_e2e_config, database=recall_database)
    stored_after_ttl: int = physical_rows(
        config=clickhouse_e2e_config, database=recall_database, where=aged
    )

    assert built.returncode == 0
    assert applied == test_case.expected_fix_statements
    assert int(cast(int, visible_before[0][0])) > 0
    assert visible_after == [[0]]
    assert stored_before_ttl > 0
    assert stored_after_ttl == 0
    assert recall_rows(project_dir, "SELECT count() FROM invocations") == [[2]]


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallDuplicateTestCase(
            description="a second delivery of every row changes no view",
            view_counts_sql=(
                "SELECT (SELECT count() FROM invocations), (SELECT count() FROM statements), "
                "(SELECT count() FROM events), (SELECT count() FROM diagnostics), "
                "(SELECT count() FROM artifacts), (SELECT sum(chunks) FROM output_invocations), "
                "(SELECT min(complete) FROM output_invocations), "
                "(SELECT count() FROM conflicts)"
            ),
            expected_physical_factor=2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_duplicate_delivery_when_queried_then_views_count_each_record_once(
    test_case: ClickHouseRecallDuplicateTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")
    before: list[list[object]] = recall_rows(project_dir, test_case.view_counts_sql)
    stored_before: int = physical_rows(config=clickhouse_e2e_config, database=recall_database)

    duplicate_recall_rows(config=clickhouse_e2e_config, database=recall_database)

    assert built.returncode == 0, built.stderr
    assert recall_rows(project_dir, test_case.view_counts_sql) == before
    assert before[0][-2:] == [1, 0]
    assert physical_rows(config=clickhouse_e2e_config, database=recall_database) == (
        stored_before * test_case.expected_physical_factor
    )
    assert run(project_dir, "recall", "output", "last", "--stream", "stdout").stdout == (
        built.stdout
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallPermissionTestCase(
            description="a read-only user gets the administrator's DDL and a successful build",
            connection_settings="settings = { readonly = 2 }\n",
            expected_fragments=(
                "Recall history is not being written",
                "Cannot execute query in readonly mode",
                "CREATE TABLE IF NOT EXISTS `{database}`.`recall_meta`",
                "CREATE OR REPLACE VIEW `{database}`.`invocations`",
                "completed successfully; only its Recall history is affected",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_store_without_create_permission_when_building_then_ddl_is_printed_and_exit_is_zero(
    test_case: ClickHouseRecallPermissionTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path,
        config=clickhouse_e2e_config,
        database=recall_database,
        settings=("", test_case.connection_settings),
    )

    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    stderr: str = built.stderr.decode(errors="replace")
    assert built.returncode == 0, stderr
    assert [
        fragment.format(database=recall_database) in stderr
        for fragment in test_case.expected_fragments
    ] == [True for _ in test_case.expected_fragments]
    assert b"Completed successfully" in built.stdout
    assert fetch_clickhouse_rows(
        config=clickhouse_e2e_config,
        sql=f"SELECT count() FROM system.tables WHERE database = '{recall_database}'",
    ) == ((0,),)


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallConcurrencyTestCase(
            description="four builds and a polling reader share one ClickHouse store",
            targets=("dev", "dev_1", "dev_2", "dev_3"),
            expected_status="completed",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_concurrent_builds_when_writing_one_store_then_every_run_is_recorded_once(
    test_case: ClickHouseRecallConcurrencyTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path,
        config=clickhouse_e2e_config,
        database=recall_database,
        targets=len(test_case.targets),
    )

    exit_codes, reads, unexpected_failures = concurrent_builds(project_dir, test_case.targets)
    recorded: list[list[object]] = recall_rows(
        project_dir,
        "SELECT i.target, i.status, o.complete FROM invocations i "
        "JOIN output_invocations o USING (invocation_id) ORDER BY i.target",
    )

    assert exit_codes == [0 for _ in test_case.targets]
    assert reads > 0
    assert unexpected_failures == 0
    assert recorded == [
        [target, test_case.expected_status, 1] for target in sorted(test_case.targets)
    ]
    assert recall_rows(
        project_dir,
        "SELECT (SELECT count() FROM conflicts), (SELECT sum(conflicts) FROM recall_delivery)",
    ) == [[0, 0]]


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallAbandonedTestCase(
            description="a SIGKILLed build is abandoned once its heartbeats go stale",
            heartbeat_seconds="0.5",
            expected_status="abandoned",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_killed_build_when_heartbeats_stop_then_the_invocation_is_abandoned(
    test_case: ClickHouseRecallAbandonedTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )

    running_id, recorded = killed_build(project_dir, heartbeat_seconds=test_case.heartbeat_seconds)

    assert recorded == [[running_id, test_case.expected_status, 1, 0]]


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallOutputTestCase(
            description="stdout alone",
            args=("--stream", "stdout"),
            expected_stream="stdout",
        ),
        ClickHouseRecallOutputTestCase(
            description="stderr alone",
            args=("--stream", "stderr"),
            expected_stream="stderr",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_build_when_recalled_from_clickhouse_then_output_is_byte_exact(
    test_case: ClickHouseRecallOutputTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    recalled: subprocess.CompletedProcess[bytes] = run(
        project_dir, "recall", "output", "last", *test_case.args
    )
    queried: subprocess.CompletedProcess[bytes] = run(
        project_dir,
        "recall",
        "query",
        "--json",
        "SELECT outcome, sql_available FROM statements WHERE outcome = 'completed' LIMIT 1",
    )

    assert recalled.returncode == 0, recalled.stderr
    assert recalled.stdout == getattr(built, test_case.expected_stream)
    assert recalled.stderr == b""
    document: dict[str, object] = json.loads(queried.stdout)
    assert document["store"] == {"adapter": "clickhouse", "database": recall_database}
    assert document["rows"] == [["completed", 1]]
    statistics: dict[str, object] = document["statistics"]  # type: ignore[assignment]
    assert isinstance(statistics["rows_read"], int)
    assert isinstance(statistics["query_id"], str)


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallRetentionConflictTestCase(
            description="a store created for 7 days is reported, never altered, for a 30-day project",
            created_with='retention = "7d"\n',
            built_with='retention = "30d"\n',
            expected_fragments=(
                "keeps history for 7 days by its table TTLs",
                "configured for 30 days",
                "MODIFY TTL recorded_at + INTERVAL 30 DAY",
                "completed successfully; only its Recall history is affected",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_store_with_another_retention_when_building_then_the_conflict_is_reported_once(
    test_case: ClickHouseRecallRetentionConflictTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    creator: Path = write_recall_project(
        parent=tmp_path / "creator",
        config=clickhouse_e2e_config,
        database=recall_database,
        settings=(test_case.created_with, ""),
    )
    assert run(creator, "build").returncode == 0
    project_dir: Path = write_recall_project(
        parent=tmp_path,
        config=clickhouse_e2e_config,
        database=recall_database,
        settings=(test_case.built_with, ""),
    )

    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")
    repeated: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    stderr: str = built.stderr.decode(errors="replace")
    assert (built.returncode, repeated.returncode) == (0, 0)
    assert [fragment in stderr for fragment in test_case.expected_fragments] == [
        True for _ in test_case.expected_fragments
    ]
    assert b"MODIFY TTL" not in repeated.stderr
    assert stored_ttl_days(config=clickhouse_e2e_config, database=recall_database)[0] == (
        "recall_artifact_refs",
        7,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallLimitedWriterTestCase(
            description="a store created from the printed script",
            between_builds=(),
            expected_recorded=[["build", "completed"], ["build", "completed"]],
        ),
        ClickHouseRecallLimitedWriterTestCase(
            description="a printed-script store whose version row expired",
            between_builds=(
                "ALTER TABLE {database}.recall_meta DELETE WHERE 1 SETTINGS mutations_sync = 2",
            ),
            expected_recorded=[["build", "completed"], ["build", "completed"]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_store_from_the_printed_ddl_when_a_select_insert_user_builds_then_history_is_written(
    test_case: ClickHouseRecallLimitedWriterTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    readonly: Path = write_recall_project(
        parent=tmp_path / "readonly",
        config=clickhouse_e2e_config,
        database=recall_database,
        settings=("", "settings = { readonly = 2 }\n"),
    )
    apply_printed_ddl(
        config=clickhouse_e2e_config,
        stderr=run(readonly, "build").stderr.decode(errors="replace"),
    )

    with limited_user(config=clickhouse_e2e_config, database=recall_database) as writer:
        project_dir: Path = write_recall_project(
            parent=tmp_path / "writer", config=writer, database=recall_database
        )
        first: subprocess.CompletedProcess[bytes] = run(project_dir, "build")
        execute_clickhouse_sql(
            config=clickhouse_e2e_config,
            statements=tuple(
                statement.format(database=recall_database) for statement in test_case.between_builds
            ),
        )
        builds: list[subprocess.CompletedProcess[bytes]] = [first, run(project_dir, "build")]
        recorded: list[list[object]] = recall_rows(
            project_dir, "SELECT command, status FROM invocations ORDER BY invocation_started_at"
        )

    assert [built.returncode for built in builds] == [0 for _ in builds]
    assert [b"Recall" in built.stderr for built in builds] == [False for _ in builds]
    assert recorded == test_case.expected_recorded


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
