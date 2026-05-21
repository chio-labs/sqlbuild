"""E2E tests for sqb seed command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.seed._test_types import SeedE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_waffle_shop,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SeedE2ETestCase(
            description="seed loads waffle_types CSV with correct data",
            expected_exit_code=0,
            expected_seed_name="waffle_types",
            expected_data=(
                (1, "Classic Belgian", "sweet", 850),
                (2, "Liege", "sweet", 950),
                (3, "Brussels", "sweet", 750),
                (4, "Cheddar Herb", "savory", 1050),
                (5, "Everything Bagel", "savory", 1100),
                (6, "Chicken and Waffle", "savory", 1450),
            ),
            expected_stdout_fragments=(
                "Seed ready (1 selected)",
                "Seeds (1)",
                "waffle_types",
                "Execution  sqb seed  (concurrency: 1)",
                "1/1  seed      waffle_types",
                "Completed successfully.",
                "PASS=1  WARN=0  FAIL=0  SKIP=0  TOTAL=1",
            ),
        ),
    ],
    ids=["seed loads waffle_types CSV with correct data"],
)
def test_given_waffle_shop_project_when_running_seed_then_seed_data_matches_expected(
    test_case: SeedE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    db_path: Path = project_dir / "waffle_shop.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "seed"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert all(fragment in result.stdout for fragment in test_case.expected_stdout_fragments)
    assert table_exists(db_path=db_path, table_name=test_case.expected_seed_name)

    seed_sql: str = (
        "SELECT waffle_type_id, waffle_name, category, price_cents "
        f"FROM main.{test_case.expected_seed_name} ORDER BY waffle_type_id"
    )
    rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=seed_sql)
    assert tuple(tuple(r) for r in rows) == test_case.expected_data
