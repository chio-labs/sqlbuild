from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.sqlite._test_types import (
    SqliteCursorWindowE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.sqlite.helpers import (
    ISO_EVENTS_CSV,
    OFFSET_EVENTS_CSV,
    build_cursor_window_files,
    model_order_ids,
    run_sqb_commands,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project

_ONE_WINDOW: tuple[str, ...] = (
    "build",
    "--start-cursor-ts",
    "2026-01-01T10:00:00",
    "--end-cursor-ts",
    "2026-01-01T10:00:00",
)
_REBUILD_WINDOWS: tuple[str, ...] = (
    "build",
    "--start-cursor-ts",
    "2026-01-01T10:00:00",
    "--end-cursor-ts",
    "2026-01-01T11:00:00",
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteCursorWindowE2ETestCase(
            description="one hourly window selects T-separated and fractional values like DuckDB",
            events_csv=ISO_EVENTS_CSV,
            commands=(_ONE_WINDOW,),
            expected_order_ids=((1,), (2,)),
        ),
        SqliteCursorWindowE2ETestCase(
            description="rebuilt windows replace their rows instead of duplicating them",
            events_csv=ISO_EVENTS_CSV,
            commands=(("build",), _REBUILD_WINDOWS),
            expected_order_ids=((1,), (2,), (4,), (5,), (6,)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_iso_timestamps_when_building_hourly_windows_then_sqlite_matches_duckdb(
    tmp_path: Path, test_case: SqliteCursorWindowE2ETestCase
) -> None:
    sqlite_dir: Path = prepare_inline_project(
        tmp_path=tmp_path / "sqlite",
        project_name="hourly_shop",
        repo_files=build_cursor_window_files(adapter="sqlite", events_csv=test_case.events_csv),
    )
    duckdb_dir: Path = prepare_inline_project(
        tmp_path=tmp_path / "duckdb",
        project_name="hourly_shop",
        repo_files=build_cursor_window_files(adapter="duckdb", events_csv=test_case.events_csv),
    )

    results: tuple[subprocess.CompletedProcess[str], ...] = (
        *run_sqb_commands(project_dir=sqlite_dir, commands=test_case.commands),
        *run_sqb_commands(project_dir=duckdb_dir, commands=test_case.commands),
    )

    assert all(result.returncode == 0 for result in results), "".join(
        result.stdout + result.stderr for result in results
    )
    assert model_order_ids(adapter="sqlite", project_dir=sqlite_dir) == (
        test_case.expected_order_ids
    )
    assert model_order_ids(adapter="duckdb", project_dir=duckdb_dir) == (
        test_case.expected_order_ids
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteCursorWindowE2ETestCase(
            description="a value with a UTC offset falls in the window of its UTC time",
            events_csv=OFFSET_EVENTS_CSV,
            commands=(_ONE_WINDOW,),
            expected_order_ids=((1,), (2,), (3,)),
        ),
        SqliteCursorWindowE2ETestCase(
            description="rebuilding the offset value's UTC window keeps one copy of it",
            events_csv=OFFSET_EVENTS_CSV,
            commands=(("build",), _ONE_WINDOW),
            expected_order_ids=((1,), (2,), (3,), (4,), (5,), (6,)),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_offset_timestamps_when_building_hourly_windows_then_sqlite_uses_utc(
    tmp_path: Path, test_case: SqliteCursorWindowE2ETestCase
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="hourly_shop",
        repo_files=build_cursor_window_files(adapter="sqlite", events_csv=test_case.events_csv),
    )

    results: tuple[subprocess.CompletedProcess[str], ...] = run_sqb_commands(
        project_dir=project_dir, commands=test_case.commands
    )

    assert all(result.returncode == 0 for result in results), "".join(
        result.stdout + result.stderr for result in results
    )
    assert model_order_ids(adapter="sqlite", project_dir=project_dir) == (
        test_case.expected_order_ids
    )
