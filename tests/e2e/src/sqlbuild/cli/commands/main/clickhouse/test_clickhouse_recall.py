from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse._test_types import (
    ClickHouseRecallAbandonedTestCase,
    ClickHouseRecallArtifactAgeTestCase,
    ClickHouseRecallBehindStoreTestCase,
    ClickHouseRecallConcurrencyTestCase,
    ClickHouseRecallDuplicateTestCase,
    ClickHouseRecallExpiredVersionTestCase,
    ClickHouseRecallExpiryTestCase,
    ClickHouseRecallFirstReleaseStoreTestCase,
    ClickHouseRecallLimitedWriterTestCase,
    ClickHouseRecallNewerStoreTestCase,
    ClickHouseRecallOutputTestCase,
    ClickHouseRecallPartialInsertTestCase,
    ClickHouseRecallPermissionTestCase,
    ClickHouseRecallPushdownTestCase,
    ClickHouseRecallQueryOutputSinkTestCase,
    ClickHouseRecallRetentionConflictTestCase,
    ClickHouseRecallRetentionTestCase,
    ClickHouseRecallUnknownRelationTestCase,
    ClickHouseRecallUnlimitedOutputTestCase,
    ClickHouseRecallUnrecordedBehindTestCase,
    ClickHouseRecallVersionRefreshTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.clickhouse.helpers import (
    FIRST_RELEASE_EDITS,
    RECALL_SCHEMA_VERSION,
    age_recorded_invocations,
    age_stored_artifacts,
    apply_printed_ddl,
    apply_printed_retention_fix,
    apply_script,
    duplicate_recall_rows,
    execute_clickhouse_sql,
    expire_recall_parts,
    fetch_clickhouse_rows,
    limited_user,
    physical_rows,
    replicate_invocations,
    stored_ttl_days,
    write_recall_project,
)
from tests.integration.src.sqlbuild.cli.recall.helpers import (
    OUTPUT_LOG_SINK,
    concurrent_builds,
    killed_build,
    killed_during_discovery,
    recall_rows,
    run,
    write_sinks,
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

    assert recorded == [[running_id, test_case.expected_status, 1, 1, 0]]


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallAbandonedTestCase(
            description="a build SIGKILLed during discovery is listed and recalled",
            heartbeat_seconds="0.5",
            expected_status="abandoned",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_build_killed_during_discovery_when_recalled_then_its_command_and_start_remain(
    test_case: ClickHouseRecallAbandonedTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )

    recorded, recalled = killed_during_discovery(
        project_dir, heartbeat_seconds=test_case.heartbeat_seconds
    )

    assert recorded == [["build", test_case.expected_status, 1]]
    assert recalled.returncode == 0, recalled.stderr
    assert f"the invocation is {test_case.expected_status}".encode() in recalled.stderr


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


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallPartialInsertTestCase(
            description="refused output inserts fail the output and leave the events delivered",
            revoked_inserts=("recall_output",),
            expected_delivery=[["events", 1, 0], ["output", 0, 1]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_one_refused_table_when_building_then_only_its_records_count_as_failed(
    test_case: ClickHouseRecallPartialInsertTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    creator: Path = write_recall_project(
        parent=tmp_path / "creator", config=clickhouse_e2e_config, database=recall_database
    )
    assert run(creator, "build").returncode == 0

    with limited_user(
        config=clickhouse_e2e_config,
        database=recall_database,
        revoked_inserts=test_case.revoked_inserts,
    ) as writer:
        built: subprocess.CompletedProcess[bytes] = run(
            write_recall_project(
                parent=tmp_path / "writer", config=writer, database=recall_database
            ),
            "build",
        )

    assert built.returncode == 0, built.stderr
    assert (
        recall_rows(
            creator,
            "SELECT stream, toUInt8(delivered = accepted), toUInt8(failed = accepted) "
            "FROM recall_delivery FINAL WHERE stream IN ('events', 'output') AND invocation_id = "
            "(SELECT invocation_id FROM invocations ORDER BY invocation_started_at DESC LIMIT 1) "
            "ORDER BY stream",
        )
        == test_case.expected_delivery
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallArtifactAgeTestCase(
            description="SQL seen past retention stays available to a reference within it",
            artifact_age_days=33,
            reference_age_days=27,
            expected_availability=[[1, 1]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_older_than_retention_when_still_referenced_then_artifacts_show_it_available(
    test_case: ClickHouseRecallArtifactAgeTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    assert run(project_dir, "build").returncode == 0
    age_recorded_invocations(
        config=clickhouse_e2e_config,
        database=recall_database,
        days=test_case.reference_age_days,
    )
    age_stored_artifacts(
        config=clickhouse_e2e_config,
        database=recall_database,
        days=test_case.artifact_age_days,
    )

    assert (
        recall_rows(
            project_dir,
            "SELECT toUInt8(count() > 0), min(available) FROM artifacts "
            "WHERE startsWith(invocation_id, 'aged-')",
        )
        == test_case.expected_availability
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallQueryOutputSinkTestCase(
            description="a read-only recall query runs no project sinks",
            sql="SELECT 'shipped_orders' AS answer",
            expected_fragment="shipped_orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_an_output_sink_when_querying_clickhouse_recall_then_the_sink_is_not_run(
    test_case: ClickHouseRecallQueryOutputSinkTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    assert run(project_dir, "build").returncode == 0
    _ = write_sinks(project_dir, {"output_log": OUTPUT_LOG_SINK})

    queried: subprocess.CompletedProcess[bytes] = run(project_dir, "recall", "query", test_case.sql)

    assert queried.returncode == 0, queried.stderr
    assert test_case.expected_fragment.encode() in queried.stdout
    assert not (project_dir / "output.log").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallFirstReleaseStoreTestCase(
            description="heartbeats without the newer columns are still written",
            expected_recorded=[["build", "completed", 1]],
            expected_notice="ADD COLUMN IF NOT EXISTS `command` Nullable(String)",
            expected_heartbeat_columns=((0,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_first_release_store_when_a_select_insert_user_builds_then_history_is_written(
    test_case: ClickHouseRecallFirstReleaseStoreTestCase,
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
        edits=FIRST_RELEASE_EDITS,
    )

    with limited_user(config=clickhouse_e2e_config, database=recall_database) as writer:
        project_dir: Path = write_recall_project(
            parent=tmp_path / "writer", config=writer, database=recall_database
        )
        built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")
        recorded: list[list[object]] = recall_rows(
            project_dir,
            "SELECT command, status, toUInt8(last_heartbeat_at IS NOT NULL) FROM invocations",
        )

    assert built.returncode == 0, built.stderr
    assert test_case.expected_notice in built.stderr.decode(errors="replace")
    assert recorded == test_case.expected_recorded
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT count() FROM system.columns WHERE database = '{recall_database}' "
            "AND table = 'recall_heartbeats' AND name IN ('command', 'subcommand')",
        )
        == test_case.expected_heartbeat_columns
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallUnlimitedOutputTestCase(
            description="output past the local store's 2 MiB default is kept whole",
            thread_lines="200000",
            expected_minimum_bytes=5 * 512 * 1024,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_large_output_when_recorded_in_clickhouse_then_no_output_limit_applies(
    test_case: ClickHouseRecallUnlimitedOutputTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    built: subprocess.CompletedProcess[bytes] = run(
        project_dir, "build", ORDERS_TASK_THREAD_LINES=test_case.thread_lines
    )

    recalled: subprocess.CompletedProcess[bytes] = run(
        project_dir, "recall", "output", "last", "--stream", "stdout"
    )

    assert built.returncode == 0, built.stderr
    assert len(built.stdout) >= test_case.expected_minimum_bytes
    assert recalled.stdout == built.stdout
    assert recalled.stderr == b""


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallBehindStoreTestCase(
            description="a SELECT, INSERT writer keeps recording and the printed DDL upgrades it",
            expected_notice="is behind this SQLBuild version, and this user may not upgrade it",
            expected_ddl_fragments=(
                "ADD COLUMN IF NOT EXISTS `command` Nullable(String);",
                "CREATE OR REPLACE VIEW `{database}`.`invocations`",
                "INSERT INTO `{database}`.`recall_meta`",
            ),
            expected_recorded=[["build", "completed"], ["build", "completed"]],
            expected_heartbeat_columns=((2,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_store_one_version_behind_when_a_select_insert_user_builds_then_it_warns_once(
    test_case: ClickHouseRecallBehindStoreTestCase,
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
        edits=FIRST_RELEASE_EDITS,
    )
    execute_clickhouse_sql(
        config=clickhouse_e2e_config,
        statements=(
            f"ALTER TABLE {recall_database}.recall_meta DELETE WHERE component = 'schema' "
            "SETTINGS mutations_sync = 2",
        ),
    )

    with (
        limited_user(config=clickhouse_e2e_config, database=recall_database) as writer,
        limited_user(
            config=clickhouse_e2e_config, database=recall_database, privileges="SELECT"
        ) as reader,
    ):
        project_dir: Path = write_recall_project(
            parent=tmp_path / "writer", config=writer, database=recall_database
        )
        reader_dir: Path = write_recall_project(
            parent=tmp_path / "reader", config=reader, database=recall_database
        )
        builds: list[subprocess.CompletedProcess[bytes]] = [
            run(project_dir, "build"),
            run(project_dir, "build"),
        ]
        recorded: list[list[object]] = recall_rows(
            reader_dir, "SELECT command, status FROM invocations ORDER BY invocation_started_at"
        )
        printed: subprocess.CompletedProcess[bytes] = run(reader_dir, "recall", "schema", "--ddl")
        apply_script(config=clickhouse_e2e_config, script=printed.stdout.decode())
        repeated: subprocess.CompletedProcess[bytes] = run(reader_dir, "recall", "schema", "--ddl")

    notices: list[int] = [
        built.stderr.decode(errors="replace").count(test_case.expected_notice) for built in builds
    ]
    ddl: str = printed.stdout.decode()
    assert [built.returncode for built in builds] == [0, 0]
    assert notices == [1, 0]
    assert recorded == test_case.expected_recorded
    assert printed.returncode == 0, printed.stderr
    assert [
        fragment.format(database=recall_database) in ddl
        for fragment in test_case.expected_ddl_fragments
    ] == [True for _ in test_case.expected_ddl_fragments]
    assert (repeated.returncode, repeated.stdout) == (0, b"")
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT count() FROM system.columns WHERE database = '{recall_database}' "
            "AND table = 'recall_heartbeats' AND name IN ('command', 'subcommand')",
        )
        == test_case.expected_heartbeat_columns
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallPushdownTestCase(
            description="statements of one invocation read only that invocation's granules",
            sql="SELECT count() > 0 FROM statements WHERE invocation_id = '{invocation_id}'",
            expected_rows=[[1]],
            max_read_fraction=0.25,
        ),
        ClickHouseRecallPushdownTestCase(
            description="statements expose invocation_started_at to bound a scan",
            sql=(
                "SELECT count() > 0 FROM statements "
                "WHERE invocation_started_at >= '{invocation_started_at}'"
            ),
            expected_rows=[[1]],
            max_read_fraction=0.25,
        ),
        ClickHouseRecallPushdownTestCase(
            description="invocations of one invocation read a bounded part of the store",
            sql="SELECT count() FROM invocations WHERE invocation_id = '{invocation_id}'",
            expected_rows=[[1]],
            max_read_fraction=0.25,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_large_store_when_filtering_a_view_then_the_filter_reaches_the_table_reads(
    test_case: ClickHouseRecallPushdownTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    assert run(project_dir, "build").returncode == 0
    replicate_invocations(
        config=clickhouse_e2e_config, database=recall_database, copies=3000, spacing_minutes=10
    )
    execute_clickhouse_sql(
        config=clickhouse_e2e_config,
        statements=(f"OPTIMIZE TABLE {recall_database}.recall_events FINAL",),
    )
    (invocation_id, started_at), *_ = fetch_clickhouse_rows(
        config=clickhouse_e2e_config,
        sql=f"SELECT invocation_id, toString(invocation_started_at) "
        f"FROM {recall_database}.recall_invocations WHERE position(invocation_id, '-') = 0",
    )
    stored_events: int = physical_rows(
        config=clickhouse_e2e_config, database=recall_database, where="1"
    )

    queried: subprocess.CompletedProcess[bytes] = run(
        project_dir,
        "recall",
        "query",
        "--json",
        test_case.sql.format(invocation_id=invocation_id, invocation_started_at=started_at),
    )

    document: dict[str, object] = json.loads(queried.stdout)
    statistics: dict[str, int] = cast(dict[str, int], document["statistics"])
    assert document["rows"] == test_case.expected_rows
    assert statistics["rows_read"] < stored_events * test_case.max_read_fraction


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallExpiredVersionTestCase(
            description="views of an older version are replaced when its version row expired",
            stale_view="SELECT invocation_id, statement_id FROM {database}.recall_events",
            expected_statement_columns=((1,),),
            expected_version=((RECALL_SCHEMA_VERSION,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_store_whose_version_row_expired_when_a_writer_with_ddl_builds_then_views_upgrade(
    test_case: ClickHouseRecallExpiredVersionTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    assert run(project_dir, "build").returncode == 0
    execute_clickhouse_sql(
        config=clickhouse_e2e_config,
        statements=(
            f"CREATE OR REPLACE VIEW {recall_database}.statements AS "
            + test_case.stale_view.format(database=recall_database),
            f"ALTER TABLE {recall_database}.recall_meta DELETE WHERE 1 SETTINGS mutations_sync = 2",
        ),
    )

    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    assert built.returncode == 0, built.stderr
    assert b"Recall" not in built.stderr
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT count() FROM system.columns WHERE database = '{recall_database}' "
            "AND table = 'statements' AND name = 'invocation_started_at'",
        )
        == test_case.expected_statement_columns
    )
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT max(toInt64OrZero(value)) FROM {recall_database}.recall_meta "
            "WHERE component = 'schema'",
        )
        == test_case.expected_version
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallUnknownRelationTestCase(
            description="a misspelled view on a complete store is the query's own error",
            sql="SELECT * FROM invocation",
            expected_fragments=("error[C974]", "invocation"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_complete_store_when_a_query_names_an_unknown_relation_then_the_server_error_shows(
    test_case: ClickHouseRecallUnknownRelationTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    assert run(project_dir, "build").returncode == 0

    queried: subprocess.CompletedProcess[bytes] = run(project_dir, "recall", "query", test_case.sql)

    stderr: str = queried.stderr.decode(errors="replace")
    assert queried.returncode == 1
    assert [fragment in stderr for fragment in test_case.expected_fragments] == [
        True for _ in test_case.expected_fragments
    ]
    assert "C971" not in stderr


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallNewerStoreTestCase(
            description="views with a column this build does not know are left alone",
            newer_view="SELECT *, 1 AS future_column FROM {database}.recall_events",
            expected_future_columns=((1,),),
            expected_version_rows=((0,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_newer_store_whose_version_row_expired_when_an_older_writer_builds_then_views_stay(
    test_case: ClickHouseRecallNewerStoreTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    assert run(project_dir, "build").returncode == 0
    execute_clickhouse_sql(
        config=clickhouse_e2e_config,
        statements=(
            f"CREATE OR REPLACE VIEW {recall_database}.statements AS "
            + test_case.newer_view.format(database=recall_database),
            f"ALTER TABLE {recall_database}.recall_meta DELETE WHERE 1 SETTINGS mutations_sync = 2",
        ),
    )

    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    assert built.returncode == 0, built.stderr
    assert b"Recall" not in built.stderr
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT count() FROM system.columns WHERE database = '{recall_database}' "
            "AND table = 'statements' AND name = 'future_column'",
        )
        == test_case.expected_future_columns
    )
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT count() FROM {recall_database}.recall_meta WHERE component = 'schema'",
        )
        == test_case.expected_version_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallVersionRefreshTestCase(
            description="a version row past half the retention is recorded again",
            row_age_days=20,
            expected_rows=((2, RECALL_SCHEMA_VERSION, 1),),
        ),
        ClickHouseRecallVersionRefreshTestCase(
            description="a recent version row is left as it is",
            row_age_days=1,
            expected_rows=((1, RECALL_SCHEMA_VERSION, 0),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_an_aging_version_row_when_building_then_it_is_refreshed_before_retention_drops_it(
    test_case: ClickHouseRecallVersionRefreshTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    project_dir: Path = write_recall_project(
        parent=tmp_path, config=clickhouse_e2e_config, database=recall_database
    )
    assert run(project_dir, "build").returncode == 0
    meta: str = f"{recall_database}.recall_meta"
    execute_clickhouse_sql(
        config=clickhouse_e2e_config,
        statements=(
            f"CREATE TABLE {recall_database}.aged_meta AS {meta}",
            f"INSERT INTO {recall_database}.aged_meta SELECT * REPLACE (recorded_at - "
            f"toIntervalDay({test_case.row_age_days}) AS recorded_at) FROM {meta} "
            "WHERE component = 'schema'",
            f"ALTER TABLE {meta} DELETE WHERE component = 'schema' SETTINGS mutations_sync = 2",
            f"INSERT INTO {meta} SELECT * FROM {recall_database}.aged_meta",
            f"DROP TABLE {recall_database}.aged_meta",
        ),
    )

    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    assert built.returncode == 0, built.stderr
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT count(), max(toInt64OrZero(value)), "
            f"countIf(recorded_at > now64(6) - toIntervalHour(1)) FROM {meta} "
            "WHERE component = 'schema'",
        )
        == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ClickHouseRecallUnrecordedBehindTestCase(
            description="a SELECT, INSERT writer warns when an expired row hides older views",
            stale_view="SELECT invocation_id, statement_id FROM {database}.recall_events",
            expected_notice="is behind this SQLBuild version, and this user may not upgrade it",
            expected_version_rows=((0,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_older_views_and_an_expired_version_row_when_a_limited_writer_builds_then_it_warns(
    test_case: ClickHouseRecallUnrecordedBehindTestCase,
    tmp_path: Path,
    clickhouse_e2e_config: dict[str, object],
    recall_database: str,
) -> None:
    admin: Path = write_recall_project(
        parent=tmp_path / "admin", config=clickhouse_e2e_config, database=recall_database
    )
    assert run(admin, "build").returncode == 0
    execute_clickhouse_sql(
        config=clickhouse_e2e_config,
        statements=(
            f"CREATE OR REPLACE VIEW {recall_database}.statements AS "
            + test_case.stale_view.format(database=recall_database),
            f"ALTER TABLE {recall_database}.recall_meta DELETE WHERE 1 SETTINGS mutations_sync = 2",
        ),
    )

    with limited_user(config=clickhouse_e2e_config, database=recall_database) as writer:
        project_dir: Path = write_recall_project(
            parent=tmp_path / "writer", config=writer, database=recall_database
        )
        built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    stderr: str = built.stderr.decode(errors="replace")
    assert built.returncode == 0, stderr
    assert stderr.count(test_case.expected_notice) == 1
    assert "sqb recall schema --ddl" in stderr
    assert (
        fetch_clickhouse_rows(
            config=clickhouse_e2e_config,
            sql=f"SELECT count() FROM {recall_database}.recall_meta WHERE component = 'schema'",
        )
        == test_case.expected_version_rows
    )
