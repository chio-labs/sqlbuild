import sqlite3
import subprocess
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.recall._test_types import (
    BehindStoreTestCase,
    ReadOnlyReaderTestCase,
    RecallConnectionErrorTestCase,
)
from tests.integration.src.sqlbuild.cli.recall.helpers import recall_rows, run, write_project

SHARED_STORE_TOML: str = (
    "\n[connections.history]\n"
    'adapter = "sqlite"\n'
    'path = "{path}"\n'
    "\n[recall]\n"
    "{keys}"
)


def _shared_project(parent: Path, *, store: Path, keys: str) -> Path:
    return write_project(
        parent / "orders_shop",
        extra_toml=SHARED_STORE_TOML.format(path=store.as_posix(), keys=keys),
    )


def _schema(store: Path) -> list[tuple[object, ...]]:
    with sqlite3.connect(store) as connection:
        return connection.execute(
            "SELECT m.type, m.name, p.name FROM sqlite_schema AS m "
            "LEFT JOIN pragma_table_xinfo(m.name) AS p ORDER BY m.type, m.name, p.cid"
        ).fetchall()


def _make_store_behind(store: Path) -> None:
    """Turn a current store into one a previous SQLBuild version wrote: no newer column, views or version."""

    with sqlite3.connect(store) as connection:
        views: list[str] = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_schema WHERE type = 'view'")
        ]
        for view in views:
            _ = connection.execute(f'DROP VIEW "{view}"')
        _ = connection.execute('ALTER TABLE "recall_heartbeats" DROP COLUMN "subcommand"')
        _ = connection.execute("DELETE FROM recall_meta WHERE component = 'schema'")


@pytest.mark.parametrize(
    "test_case",
    [
        RecallConnectionErrorTestCase(
            description="the removed connection key names its replacements on a build",
            recall_toml='[recall]\nconnection = "history"\n',
            args=("build",),
            expected_message=(
                "recall.connection was replaced by write_connection and read_connection: "
                'set write_connection = "history" and read_connection = "history"'
            ),
        ),
        RecallConnectionErrorTestCase(
            description="the removed connection key fails recall queries too",
            recall_toml='[targets.dev.recall]\nconnection = "history"\n',
            args=("recall", "query", "SELECT 1"),
            expected_message="targets.dev.recall.connection was replaced by write_connection",
        ),
        RecallConnectionErrorTestCase(
            description="a write connection without a read connection is rejected",
            recall_toml='[recall]\nwrite_connection = "history"\n',
            args=("build",),
            expected_message="recall.write_connection requires recall.read_connection",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_recall_connections_when_running_then_the_command_fails_naming_the_keys(
    test_case: RecallConnectionErrorTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(
        tmp_path / "orders_shop",
        extra_toml=(
            '\n[connections.history]\nadapter = "sqlite"\npath = "history.sqlite3"\n\n'
            + test_case.recall_toml
        ),
    )

    completed: subprocess.CompletedProcess[bytes] = run(project_dir, *test_case.args)

    assert completed.returncode != 0
    assert test_case.expected_message in completed.stderr.decode(errors="replace")
    assert not (project_dir / "history.sqlite3").exists()


@pytest.mark.parametrize(
    "test_case",
    [
        ReadOnlyReaderTestCase(
            description="a reader sees shared history and records its own runs locally",
            expected_shared_invocations=[["build", "completed"]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_only_a_read_connection_when_running_then_reads_are_shared_and_writes_local(
    test_case: ReadOnlyReaderTestCase, tmp_path: Path
) -> None:
    store: Path = tmp_path / "shared" / "history.sqlite3"
    writer: Path = _shared_project(
        tmp_path / "writer",
        store=store,
        keys='write_connection = "history"\nread_connection = "history"\n',
    )
    assert run(writer, "build").returncode == 0
    reader: Path = _shared_project(
        tmp_path / "reader", store=store, keys='read_connection = "history"\n'
    )
    schema_before: list[tuple[object, ...]] = _schema(store)

    built: subprocess.CompletedProcess[bytes] = run(reader, "build")
    shared: list[list[object]] = recall_rows(reader, "SELECT command, status FROM invocations")

    assert built.returncode == 0, built.stderr.decode(errors="replace")
    assert b"Recall" not in built.stderr
    assert shared == test_case.expected_shared_invocations
    assert (reader / "logs" / "recall.sqlite3").exists()
    assert _schema(store) == schema_before


@pytest.mark.parametrize(
    "test_case",
    [
        BehindStoreTestCase(
            description="readers print the upgrade without applying it, and it applies cleanly",
            expected_ddl_fragments=(
                'ALTER TABLE "recall_heartbeats" ADD COLUMN "subcommand" TEXT;',
                'DROP VIEW IF EXISTS "invocations";',
                'CREATE VIEW IF NOT EXISTS "invocations" AS',
                "INSERT OR IGNORE INTO \"recall_meta\"",
            ),
            expected_up_to_date_note="is up to date with this SQLBuild version",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_store_one_version_behind_when_read_then_no_ddl_runs_and_the_printed_ddl_applies(
    test_case: BehindStoreTestCase, tmp_path: Path
) -> None:
    store: Path = tmp_path / "shared" / "history.sqlite3"
    project_dir: Path = _shared_project(
        tmp_path,
        store=store,
        keys='write_connection = "history"\nread_connection = "history"\n',
    )
    assert run(project_dir, "build").returncode == 0
    _make_store_behind(store)
    schema_before: list[tuple[object, ...]] = _schema(store)

    queried: subprocess.CompletedProcess[bytes] = run(
        project_dir, "recall", "query", "SELECT count(*) FROM recall_invocations"
    )
    printed: subprocess.CompletedProcess[bytes] = run(project_dir, "recall", "schema", "--ddl")
    schema_after_reads: list[tuple[object, ...]] = _schema(store)
    with sqlite3.connect(store) as connection:
        connection.executescript(printed.stdout.decode())
    repeated: subprocess.CompletedProcess[bytes] = run(project_dir, "recall", "schema", "--ddl")
    rebuilt: subprocess.CompletedProcess[bytes] = run(project_dir, "build")

    ddl: str = printed.stdout.decode()
    assert (queried.returncode, printed.returncode, repeated.returncode) == (0, 0, 0)
    assert schema_after_reads == schema_before
    assert [fragment in ddl for fragment in test_case.expected_ddl_fragments] == [
        True for _ in test_case.expected_ddl_fragments
    ]
    assert "CREATE TABLE" not in ddl
    assert repeated.stdout == b""
    assert test_case.expected_up_to_date_note in repeated.stderr.decode()
    assert rebuilt.returncode == 0
    assert b"Recall" not in rebuilt.stderr
    assert recall_rows(project_dir, "SELECT count(*) FROM invocations") == [[2]]
