import json
import os
import subprocess
from pathlib import Path

import jsonschema
import pytest

from tests.integration.src.sqlbuild.cli.recall._test_types import (
    AbandonedRunTestCase,
    CombinedOutputTestCase,
    ConcurrentBuildsTestCase,
    DisabledRecallTestCase,
    JsonQueryTestCase,
    ReadOnlyStoreTestCase,
    RecallOutputTestCase,
    RecallRejectionTestCase,
    RecordedFactsTestCase,
    RepeatedBuildTestCase,
    TextOutputTestCase,
)
from tests.integration.src.sqlbuild.cli.recall.helpers import (
    EMITTED_STDERR,
    EMITTED_STDOUT,
    EMITTED_TAIL,
    build_with_read_only_logs,
    concurrent_builds,
    killed_build,
    recall_rows,
    run,
    write_project,
)

RECALL_QUERY_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": [
        "backend",
        "target",
        "store",
        "columns",
        "rows",
        "row_count",
        "truncated",
        "limit",
        "statistics",
    ],
    "additionalProperties": False,
    "properties": {
        "backend": {"const": "logs"},
        "target": {"type": ["string", "null"]},
        "store": {
            "type": "object",
            "required": ["adapter", "database"],
            "properties": {"adapter": {"const": "sqlite"}, "database": {"type": "string"}},
        },
        "columns": {"type": "array", "items": {"type": "string"}},
        "rows": {"type": "array", "items": {"type": "array"}},
        "row_count": {"type": "integer", "minimum": 0},
        "truncated": {"type": "boolean"},
        "limit": {"type": ["integer", "null"]},
        "statistics": {
            "type": "object",
            "required": ["elapsed_ms", "rows_read", "bytes_read", "query_id"],
            "properties": {
                "elapsed_ms": {"type": "number"},
                "rows_read": {"type": "null"},
                "bytes_read": {"type": "null"},
                "query_id": {"type": "null"},
            },
        },
    },
}
DISABLED_TARGET: str = "\n[targets.dev.recall]\nenabled = false\n"
POSIX_PERMISSIONS: bool = os.name == "posix" and os.geteuid() != 0


@pytest.mark.parametrize(
    "test_case",
    [
        RecallOutputTestCase(
            description="stdout", args=("--stream", "stdout"), expected_stream="stdout"
        ),
        RecallOutputTestCase(
            description="stderr", args=("--stream", "stderr"), expected_stream="stderr"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_build_with_binary_output_when_recalled_then_each_stream_is_byte_exact(
    test_case: RecallOutputTestCase,
    built_project: tuple[Path, subprocess.CompletedProcess[bytes]],
) -> None:
    project_dir, built = built_project

    recalled: subprocess.CompletedProcess[bytes] = run(
        project_dir, "recall", "output", "last", *test_case.args
    )

    assert recalled.returncode == 0, recalled.stderr
    assert recalled.stdout == getattr(built, test_case.expected_stream)
    assert recalled.stderr == b""


@pytest.mark.parametrize(
    "test_case",
    [
        CombinedOutputTestCase(
            description="stdout, then the stderr warning, then more stdout",
            expected_order=(EMITTED_STDOUT, EMITTED_STDERR, EMITTED_TAIL),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_interleaved_writes_when_recalled_combined_then_order_is_preserved(
    test_case: CombinedOutputTestCase,
    built_project: tuple[Path, subprocess.CompletedProcess[bytes]],
) -> None:
    project_dir, built = built_project

    combined: bytes = run(project_dir, "recall", "output", "last").stdout
    transcript: list[list[object]] = recall_rows(
        project_dir,
        "SELECT hex(stdout), hex(stderr) FROM output_transcripts t "
        "JOIN output_invocations o USING (invocation_id) WHERE o.complete = 1",
    )

    positions: list[int] = [combined.index(piece) for piece in test_case.expected_order]
    assert positions == sorted(positions)
    assert len(combined) == len(built.stdout) + len(built.stderr)
    assert transcript == [[built.stdout.hex().upper(), built.stderr.hex().upper()]]


@pytest.mark.parametrize(
    "test_case",
    [
        RecordedFactsTestCase(
            description="the invocation carries its command, target and adapter",
            sql="SELECT status, command, target, adapter, exit_code FROM invocations",
            expected_rows=[["completed", "build", "dev", "duckdb", 0]],
        ),
        RecordedFactsTestCase(
            description="every statement completed and kept its SQL",
            sql="SELECT COUNT(*) > 0, SUM(outcome = 'completed') = COUNT(*), "
            "SUM(sql_available) = COUNT(*) FROM statements",
            expected_rows=[[1, 1, 1]],
        ),
        RecordedFactsTestCase(
            description="natively encoded events keep payloads, promotions and UTC timestamps",
            sql="SELECT COUNT(*) > 0, "
            "SUM(payload = '{}' OR statement_kind IS NULL OR intent IS NULL), "
            "SUM(occurred_at NOT GLOB "
            "'[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]Z'), "
            "SUM(invocation_sequence IS NULL) "
            "FROM events WHERE event_type LIKE 'statement_%'",
            expected_rows=[[1, 0, 0, 0]],
        ),
        RecordedFactsTestCase(
            description="the started event names target and adapter",
            sql="SELECT json_extract(payload, '$.target'), json_extract(payload, '$.adapter') "
            "FROM events WHERE event_type = 'invocation_started'",
            expected_rows=[["dev", "duckdb"]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_build_when_recalled_then_invocation_statements_and_events_are_queryable(
    test_case: RecordedFactsTestCase,
    built_project: tuple[Path, subprocess.CompletedProcess[bytes]],
) -> None:
    project_dir, _ = built_project

    rows: list[list[object]] = recall_rows(project_dir, test_case.sql)

    assert rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        JsonQueryTestCase(
            description="a limited query reports truncation",
            args=(
                "--limit",
                "1",
                "SELECT invocation_id, data FROM recall_output ORDER BY sequence",
            ),
            expected_row_count=1,
            expected_truncated=True,
            expected_columns=["invocation_id", "data"],
        ),
        JsonQueryTestCase(
            description="an unlimited query is complete",
            args=("--no-limit", "SELECT COUNT(*) AS total FROM invocations"),
            expected_row_count=1,
            expected_truncated=False,
            expected_columns=["total"],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_recall_query_when_rendered_as_json_then_it_matches_the_schema(
    test_case: JsonQueryTestCase,
    built_project: tuple[Path, subprocess.CompletedProcess[bytes]],
) -> None:
    project_dir, _ = built_project

    queried: subprocess.CompletedProcess[bytes] = run(
        project_dir, "recall", "query", "--json", *test_case.args
    )

    document: dict[str, object] = json.loads(queried.stdout)
    jsonschema.validate(document, RECALL_QUERY_SCHEMA)
    assert document["row_count"] == test_case.expected_row_count
    assert document["truncated"] is test_case.expected_truncated
    assert document["columns"] == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        TextOutputTestCase(
            description="long cells are truncated with the remaining byte count",
            args=(
                "query",
                "--max-cell-bytes",
                "8",
                "SELECT 'first line' || char(10) || 'second line' AS note",
            ),
            expected_fragments=("note | first li…[+14 bytes]", "1 row"),
        ),
        TextOutputTestCase(
            description="the schema lists views and join keys",
            args=("schema",),
            expected_fragments=(
                "output_transcripts (view)",
                "invocation_id TEXT not null  join key",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recall_text_output_when_rendered_then_cells_and_schema_are_readable(
    test_case: TextOutputTestCase,
    built_project: tuple[Path, subprocess.CompletedProcess[bytes]],
) -> None:
    project_dir, _ = built_project

    rendered: subprocess.CompletedProcess[bytes] = run(project_dir, "recall", *test_case.args)

    stdout: str = rendered.stdout.decode()
    assert rendered.returncode == 0
    assert [fragment in stdout for fragment in test_case.expected_fragments] == [
        True for _ in test_case.expected_fragments
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        RecallRejectionTestCase(
            description="disabled target",
            project_suffix=DISABLED_TARGET,
            args=("recall", "query", "SELECT 1"),
            expected_code="C970",
        ),
        RecallRejectionTestCase(
            description="unknown invocation",
            project_suffix="",
            args=("recall", "output", "no-such-invocation"),
            expected_code="C972",
        ),
        RecallRejectionTestCase(
            description="write statement",
            project_suffix="",
            args=("recall", "query", "DELETE FROM recall_output"),
            expected_code="C974",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_recall_requests_when_run_then_coded_errors_are_reported(
    test_case: RecallRejectionTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop", extra_toml=test_case.project_suffix)
    _ = run(project_dir, "build")

    rejected: subprocess.CompletedProcess[bytes] = run(project_dir, *test_case.args)

    assert rejected.returncode == 1
    assert f"[{test_case.expected_code}]" in rejected.stderr.decode()


@pytest.mark.parametrize(
    "test_case",
    [
        DisabledRecallTestCase(
            description="a disabled target writes no store",
            project_suffix=DISABLED_TARGET,
            expected_store_exists=False,
        ),
        DisabledRecallTestCase(
            description="the default writes the local store",
            project_suffix="",
            expected_store_exists=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recall_settings_when_building_then_the_local_store_follows_them(
    test_case: DisabledRecallTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop", extra_toml=test_case.project_suffix)

    built: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    assert built.returncode == 0
    assert (project_dir / "logs" / "recall.sqlite3").exists() is test_case.expected_store_exists


@pytest.mark.skipif(not POSIX_PERMISSIONS, reason="needs POSIX permissions as a non-root user")
@pytest.mark.parametrize(
    "test_case",
    [
        ReadOnlyStoreTestCase(
            description="the notice carries the DDL once and the build still succeeds",
            expected_fragments=(
                "Recall history is not being written for target `dev`",
                'CREATE TABLE IF NOT EXISTS "recall_output"',
                'CREATE VIEW IF NOT EXISTS "invocations"',
            ),
            expected_repeat_notice=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_read_only_logs_directory_when_building_then_ddl_is_printed_and_exit_is_zero(
    test_case: ReadOnlyStoreTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop")

    built, repeated = build_with_read_only_logs(project_dir)

    stderr: str = built.stderr.decode(errors="replace")
    assert (built.returncode, repeated.returncode) == (0, 0)
    assert [fragment in stderr for fragment in test_case.expected_fragments] == [
        True for _ in test_case.expected_fragments
    ]
    assert "Completed successfully" in built.stdout.decode(errors="replace")
    assert (
        "Recall history is not being written" in repeated.stderr.decode(errors="replace")
    ) is test_case.expected_repeat_notice


@pytest.mark.parametrize(
    "test_case",
    [
        AbandonedRunTestCase(
            description="a SIGKILLed build is abandoned with incomplete output",
            heartbeat_seconds="0.3",
            expected_status="abandoned",
            expected_output_complete=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_killed_build_when_heartbeats_stop_then_the_invocation_is_abandoned(
    test_case: AbandonedRunTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop")

    running_id, recorded = killed_build(project_dir, heartbeat_seconds=test_case.heartbeat_seconds)

    assert recorded == [
        [running_id, test_case.expected_status, 1, test_case.expected_output_complete]
    ]


@pytest.mark.parametrize(
    "test_case",
    [
        ConcurrentBuildsTestCase(
            description="four builds and a polling reader share one store",
            targets=("dev", "dev_1", "dev_2", "dev_3"),
            expected_status="completed",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_four_concurrent_builds_and_a_reader_when_run_then_every_run_is_recorded(
    test_case: ConcurrentBuildsTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop", targets=len(test_case.targets))

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


@pytest.mark.parametrize(
    "test_case",
    [
        RepeatedBuildTestCase(
            description="repeated SQL is shared, never a conflict",
            builds=2,
            sql="SELECT (SELECT COUNT(*) FROM conflicts), "
            "(SELECT SUM(conflicts) FROM recall_delivery)",
            expected_rows=[[0, 0]],
        ),
        RepeatedBuildTestCase(
            description="every stream of every build delivers exactly what it accepted",
            builds=2,
            sql="SELECT COUNT(DISTINCT invocation_id), "
            "SUM(accepted != delivered + filtered + dropped + failed), "
            "SUM(dropped + failed), MIN(flush_complete) FROM recall_delivery",
            expected_rows=[[2, 0, 0, 1]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_identical_builds_when_recorded_then_artifacts_and_delivery_counts_stay_exact(
    test_case: RepeatedBuildTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop")

    exit_codes: list[int] = [run(project_dir, "build").returncode for _ in range(test_case.builds)]
    rows: list[list[object]] = recall_rows(project_dir, test_case.sql)

    assert exit_codes == [0 for _ in range(test_case.builds)]
    assert rows == test_case.expected_rows
