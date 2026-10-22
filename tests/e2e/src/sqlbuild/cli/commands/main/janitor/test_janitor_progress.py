"""E2E tests for janitor progress output, inspection reads, concurrency and audit batching."""

from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.janitor._test_types import (
    JanitorConcurrencyE2ETestCase,
    JanitorInspectionCountE2ETestCase,
    JanitorJsonE2ETestCase,
    JanitorProgressE2ETestCase,
    JanitorShortenedArchiveE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.janitor.helpers import (
    janitor_end_state,
    prepare_probe_janitor_project,
    read_probe_statements,
    write_probe_settings,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    query_duckdb,
    run_sqb,
    table_exists,
)

ITEM_LINE: re.Pattern[str] = re.compile(r"^\s+(?P<index>\d+)/(?P<total>\d+)  (?P<action>\w+)\s")


def _assert_in_order(output: str, lines: tuple[str, ...]) -> None:
    position: int = 0
    line: str
    for line in lines:
        found: int = output.find(line, position)
        assert found >= 0, f"{line!r} missing after position {position} in:\n{output}"
        position = found + len(line)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorProgressE2ETestCase(
            description="each phase announces its work, streams each action and closes",
            janitor_command=("--no-color", "janitor", "--auto-approve"),
            stale_tables=12,
            expected_exit_code=0,
            expected_ordered_lines=(
                "Janitor preview  default",
                "Relations to archive",
                "  main.old_orders_009  ->  main._sqb_archive__",
                "  ... and 2 more (use --verbose to show all)",
                "Skipped objects (",
                "Archiving 12 relations...",
                "   1/12  archived  main.old_orders_000 -> main._sqb_archive__",
                "  OK  ",
                "  12/12  archived  main.old_orders_011 -> main._sqb_archive__",
                "Archived 12 relations. (",
                "Deleting 1 expired archive...",
                "  1/1  deleted   main._sqb_archive__20200101t000000z__old_products  OK",
                "Deleted 1 expired archive. (",
                "Pruning 1 direct state table...",
                "  1/1  pruned    main._sqlbuild_fingerprints  OK",
                "Pruned 1 direct state table. (",
                "\u2713 Janitor completed  archived 12, deleted 1, pruned 1  (",
            ),
            unexpected_fragments=(
                "  main.old_orders_010  ->  ",
                "main._sqlbuild_fingerprints  relation matches exclude pattern",
            ),
        ),
        JanitorProgressE2ETestCase(
            description="verbose preview lists every relation and skipped object",
            janitor_command=("--no-color", "janitor", "--auto-approve", "--verbose"),
            stale_tables=12,
            expected_exit_code=0,
            expected_ordered_lines=(
                "  main.old_orders_011  ->  main._sqb_archive__",
                "Skipped objects\n  main._sqlbuild_fingerprints  relation matches exclude pattern",
                "\u2713 Janitor completed  archived 12, deleted 1, pruned 1  (",
            ),
            unexpected_fragments=("... and", "Skipped objects ("),
        ),
        JanitorProgressE2ETestCase(
            description="a failing rename keeps earlier lines, marks the item and fails the run",
            janitor_command=("--no-color", "janitor", "--auto-approve"),
            stale_tables=12,
            expected_exit_code=1,
            fail_rename="old_orders_005",
            expected_ordered_lines=(
                "Archiving 12 relations...",
                "   5/12  archived  main.old_orders_004 -> main._sqb_archive__",
                "   6/12  archived  main.old_orders_005 -> main._sqb_archive__",
                "  FAIL  ",
                "simulated rename failure for old_orders_005",
                "\u2717 Archiving failed  after 5 of 12 relations  (",
                "\u2717 Janitor failed  archived 5, deleted 0, pruned 0  (",
            ),
            unexpected_fragments=("7/12", "Deleting 1 expired archive", "Janitor completed"),
            expected_archive_events=5,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_stale_relations_when_running_janitor_then_progress_streams_in_order(
    test_case: JanitorProgressE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_probe_janitor_project(
        tmp_path=tmp_path,
        project_name="janitor_progress",
        stale_tables={"main": test_case.stale_tables},
    )
    write_probe_settings(project_dir=project_dir, fail_rename=test_case.fail_rename)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command, project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    _assert_in_order(result.stdout, test_case.expected_ordered_lines)
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result.stdout
    if test_case.expected_archive_events is not None:
        db_path: Path = project_dir / "janitor.duckdb"
        assert query_duckdb(
            db_path=db_path,
            sql="SELECT count(*) FROM main._sqlbuild_janitor_events WHERE event_type = 'archive'",
        ) == [(test_case.expected_archive_events,)]
        assert table_exists(db_path=db_path, table_name=test_case.fail_rename or "")


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorJsonE2ETestCase(
            description="stdout is one JSON document and progress goes to stderr",
            janitor_command=("janitor", "--auto-approve", "--json"),
            stale_tables=3,
            expected_status="completed",
            expected_archived=3,
            expected_stderr_fragments=(
                "Janitor preview  default",
                "Archiving 3 relations...",
                "  1/3  archived  main.old_orders_000 -> main._sqb_archive__",
                "\u2713 Janitor completed  archived 3, deleted 1, pruned 1",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_json_flag_when_running_janitor_then_stdout_holds_plan_and_result(
    test_case: JanitorJsonE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_probe_janitor_project(
        tmp_path=tmp_path,
        project_name="janitor_json",
        stale_tables={"main": test_case.stale_tables},
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.janitor_command, project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["status"] == test_case.expected_status
    assert len(payload["plan"]["relations_to_archive"]) == test_case.stale_tables
    assert payload["result"]["counts"]["archived"] == test_case.expected_archived
    assert [item["status"] for item in payload["result"]["items"]] == ["ok"] * (
        test_case.stale_tables + 2
    )
    assert payload["error"] is None
    _assert_in_order(result.stderr, test_case.expected_stderr_fragments)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorInspectionCountE2ETestCase(
            description="each schema is listed once, its views read once, and events chunked",
            stale_tables={"main": 150, "mart": 3, "staging": 3},
            renamed_models=("revenue", "customers"),
            expected_listings_per_schema=1,
            expected_view_definition_reads=3,
            expected_event_inserts={"main": 3, "mart": 2, "staging": 2},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_several_schemas_when_running_janitor_then_reads_and_writes_scale_per_schema(
    test_case: JanitorInspectionCountE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_probe_janitor_project(
        tmp_path=tmp_path,
        project_name="janitor_counts",
        stale_tables=test_case.stale_tables,
        renamed_models=test_case.renamed_models,
    )
    write_probe_settings(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "janitor", "--auto-approve"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    statements: tuple[str, ...] = read_probe_statements(project_dir=project_dir)
    schema: str
    for schema in test_case.stale_tables:
        listings: tuple[str, ...] = tuple(
            statement
            for statement in statements
            if "FROM information_schema.tables" in statement
            and f"table_schema IN ('{schema}')" in statement
            and "table_catalog" not in statement
        )
        assert len(listings) == test_case.expected_listings_per_schema, listings
        existence: tuple[str, ...] = tuple(
            statement
            for statement in statements
            if statement.startswith(f"SELECT event_id FROM {schema}._sqlbuild_janitor_events")
        )
        assert len(existence) == 1, existence
        inserts: int = sum(
            statement.startswith(f"INSERT INTO {schema}._sqlbuild_janitor_events")
            for statement in statements
        )
        archived: int = test_case.stale_tables[schema]
        assert inserts == test_case.expected_event_inserts[schema] == math.ceil(archived / 100) + 1
    assert not any(
        "FROM information_schema.tables" in statement and "', '" in statement
        for statement in statements
    )
    view_reads: tuple[str, ...] = tuple(
        statement for statement in statements if "FROM duckdb_views()" in statement
    )
    assert len(view_reads) == test_case.expected_view_definition_reads, view_reads
    assert all(" IN (" in statement for statement in view_reads)


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorConcurrencyE2ETestCase(
            description="concurrent actions leave the same end state as sequential ones",
            stale_tables={"main": 30, "staging": 5},
            concurrency=4,
            fail_rename=None,
            expected_exit_code=0,
        ),
        JanitorConcurrencyE2ETestCase(
            description="a failing concurrent rename is reported alone and events stay complete",
            stale_tables={"main": 30},
            concurrency=4,
            fail_rename="old_orders_012",
            expected_exit_code=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_concurrent_adapter_when_running_janitor_then_matches_sequential_end_state(
    test_case: JanitorConcurrencyE2ETestCase, tmp_path: Path
) -> None:
    sequential_dir: Path = prepare_probe_janitor_project(
        tmp_path=tmp_path / "sequential",
        project_name="janitor_sequential",
        stale_tables=test_case.stale_tables,
    )
    concurrent_dir: Path = prepare_probe_janitor_project(
        tmp_path=tmp_path / "concurrent",
        project_name="janitor_concurrent",
        stale_tables=test_case.stale_tables,
        concurrency=test_case.concurrency,
    )
    write_probe_settings(project_dir=sequential_dir)
    write_probe_settings(
        project_dir=concurrent_dir,
        concurrent_ddl_limit=test_case.concurrency,
        fail_rename=test_case.fail_rename,
    )
    command: tuple[str, ...] = ("--no-color", "janitor", "--auto-approve")

    sequential: subprocess.CompletedProcess[str] = run_sqb(
        command=command, project_dir=sequential_dir
    )
    concurrent: subprocess.CompletedProcess[str] = run_sqb(
        command=command, project_dir=concurrent_dir
    )

    assert sequential.returncode == 0, sequential.stdout + sequential.stderr
    assert concurrent.returncode == test_case.expected_exit_code, (
        concurrent.stdout + concurrent.stderr
    )
    total: int = sum(test_case.stale_tables.values())
    archive_lines: list[re.Match[str]] = [
        match
        for line in concurrent.stdout.splitlines()
        if (match := ITEM_LINE.match(line)) is not None and match["action"] == "archived"
    ]
    assert [int(match["index"]) for match in archive_lines] == list(
        range(1, len(archive_lines) + 1)
    )
    assert {int(match["total"]) for match in archive_lines} == {total}
    assert f"Connecting to probe_janitor_duckdb ({test_case.concurrency - 1} connections)" in (
        concurrent.stdout
    )
    concurrent_db: Path = concurrent_dir / "janitor.duckdb"
    if test_case.fail_rename is None:
        assert len(archive_lines) == total
        assert janitor_end_state(db_path=concurrent_db) == janitor_end_state(
            db_path=sequential_dir / "janitor.duckdb"
        )
        return
    assert sum(" FAIL " in line for line in concurrent.stdout.splitlines()) == 1
    assert "\u2717 Janitor failed  archived" in concurrent.stdout
    assert table_exists(db_path=concurrent_db, table_name=test_case.fail_rename)
    renamed: list[tuple[object, ...]] = query_duckdb(
        db_path=concurrent_db,
        sql=(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name LIKE '\\_sqb\\_archive\\_\\_%old\\_orders%' "
            "ESCAPE '\\'"
        ),
    )
    assert query_duckdb(
        db_path=concurrent_db,
        sql="SELECT count(*) FROM main._sqlbuild_janitor_events WHERE event_type = 'archive'",
    ) == renamed


@pytest.mark.parametrize(
    "test_case",
    [
        JanitorShortenedArchiveE2ETestCase(
            description="a shortened archive name gets its event right after its rename",
            long_relation_name="legacy_orders_with_a_very_long_descriptive_name_kept_for_audit",
            identifier_limit=48,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_shortened_archive_name_when_archiving_then_event_is_written_immediately(
    test_case: JanitorShortenedArchiveE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_probe_janitor_project(
        tmp_path=tmp_path, project_name="janitor_shortened", stale_tables={"main": 3}
    )
    execute_duckdb(
        db_path=project_dir / "janitor.duckdb",
        sql=f"CREATE TABLE main.{test_case.long_relation_name} AS SELECT 1 AS id",
    )
    write_probe_settings(project_dir=project_dir, identifier_limit=test_case.identifier_limit)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "janitor", "--auto-approve"), project_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    statements: tuple[str, ...] = read_probe_statements(project_dir=project_dir)
    rename: int = next(
        index
        for index, statement in enumerate(statements)
        if statement.startswith(f"ALTER TABLE main.{test_case.long_relation_name} RENAME")
    )
    assert statements[rename + 1].startswith("INSERT INTO main._sqlbuild_janitor_events")
    assert f"'{test_case.long_relation_name}'" in statements[rename + 1]
    assert statements[rename + 1].count("), (") == 0
    assert query_duckdb(
        db_path=project_dir / "janitor.duckdb",
        sql=(
            "SELECT count(*) FROM main._sqlbuild_janitor_events "
            f"WHERE original_name = '{test_case.long_relation_name}'"
        ),
    ) == [(1,)]
