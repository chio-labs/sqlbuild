from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.sqlite._test_types import (
    SqliteLoaderE2ETestCase,
    SqliteWaffleShopE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.sqlite.helpers import (
    LOADED_EVENT_ROWS_SQL,
    LOADED_EVENT_TYPES_SQL,
    LOADER_PROJECT_FILES,
    SQLITE_FILE,
    prepare_sqlite_waffle_shop,
    run_sqb_commands,
    sqlite_rows,
    waffle_row_counts,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    prepare_waffle_shop,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteWaffleShopE2ETestCase(
            description="waffle shop full build succeeds on sqlite",
            commands=(("build",), ("test",), ("build",)),
            expected_fragments=("Completed successfully", "FAIL=0", "Completed successfully"),
            expected_row_counts={
                "raw_customers": 5,
                "raw_orders": 10,
                "waffle_types": 6,
                "stg_customers": 5,
                "stg_orders": 10,
                "stg_payments": 8,
                "fact_orders": 10,
                "dim_customers": 5,
                "daily_revenue": 3,
                "scenario_order_prices": 10,
                "customer_status_snapshot": 5,
                "order_status_index": 10,
                "hourly_order_activity": 8,
                "daily_activity_rollup": 3,
                "hourly_activity_with_daily_context": 0,
            },
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_waffle_shop_when_building_testing_and_rebuilding_on_sqlite_then_rows_match_duckdb(
    tmp_path: Path, test_case: SqliteWaffleShopE2ETestCase
) -> None:
    project_dirs: dict[str, Path] = {
        "sqlite": prepare_sqlite_waffle_shop(tmp_path=tmp_path / "sqlite"),
        "duckdb": prepare_waffle_shop(tmp_path / "duckdb"),
    }
    row_counts: dict[str, dict[str, int]] = {}
    adapter: str
    project_dir: Path
    for adapter, project_dir in project_dirs.items():
        results: tuple[subprocess.CompletedProcess[str], ...] = run_sqb_commands(
            project_dir=project_dir, commands=test_case.commands
        )
        result: subprocess.CompletedProcess[str]
        fragment: str
        for result, fragment in zip(results, test_case.expected_fragments, strict=True):
            output: str = result.stdout + result.stderr
            assert result.returncode == test_case.expected_return_code, (adapter, output)
            assert fragment in result.stdout, (adapter, output)
        row_counts[adapter] = waffle_row_counts(adapter=adapter, project_dir=project_dir)

    assert row_counts["sqlite"] == row_counts["duckdb"]
    assert row_counts["sqlite"] == test_case.expected_row_counts


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteLoaderE2ETestCase(
            description="loaded timestamps and dates stay ISO text under their declared types",
            builds=2,
            relations=("raw_events", "events"),
            expected_rows=(
                (1, "2026-04-01 09:15:00", "2026-04-01", "2026-04-01 09:30:00"),
                (2, "2026-04-02 08:45:30.25", "2026-04-02", None),
            ),
            expected_declared_types=(
                ("event_id", "INTEGER"),
                ("happened_at", "TIMESTAMP"),
                ("event_day", "DATE"),
                ("logged_at", "TIMESTAMP"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_loader_with_timestamps_when_building_on_sqlite_then_values_are_kept(
    tmp_path: Path, test_case: SqliteLoaderE2ETestCase
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="events_shop", repo_files=LOADER_PROJECT_FILES
    )

    results: tuple[subprocess.CompletedProcess[str], ...] = run_sqb_commands(
        project_dir=project_dir, commands=(("build",),) * test_case.builds
    )

    assert [result.returncode for result in results] == [0] * test_case.builds, [
        result.stdout + result.stderr for result in results
    ]
    db_path: Path = project_dir / SQLITE_FILE
    relation: str
    for relation in test_case.relations:
        assert (
            sqlite_rows(db_path=db_path, sql=LOADED_EVENT_ROWS_SQL.format(relation=relation))
            == test_case.expected_rows
        )
    assert sqlite_rows(db_path=db_path, sql=LOADED_EVENT_TYPES_SQL) == (
        test_case.expected_declared_types
    )
