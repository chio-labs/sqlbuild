"""E2E coverage for governed runtime-dynamic pivot columns."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    DynamicColumnContractE2ETestCase,
    DynamicColumnRejectionE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import dynamic_category_project
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import query_duckdb, run_sqb


@pytest.mark.parametrize(
    "test_case",
    (
        DynamicColumnContractE2ETestCase(
            description="generated category columns are enforced",
            expected_rows=((1, "10.25", "20.50"), (2, "7.00", None)),
        ),
        DynamicColumnContractE2ETestCase(
            description="a name pattern must match each generated column name whole",
            expected_rows=((1, "10.25", "20.50"), (2, "7.00", None)),
            name_pattern_entry=",\n      name_pattern 'books|games'",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dynamic_pivot_contract_when_building_then_generated_columns_are_type_checked(
    test_case: DynamicColumnContractE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = dynamic_category_project(
        tmp_path=tmp_path, name_pattern_entry=test_case.name_pattern_entry
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            "SELECT customer_id, CAST(books AS VARCHAR), CAST(games AS VARCHAR) "
            "FROM main.customer_category_amounts ORDER BY customer_id"
        ),
    )
    assert tuple(rows) == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    (
        DynamicColumnRejectionE2ETestCase(
            description="a pattern matching only part of a generated column name rejects it",
            name_pattern_entry=",\n      name_pattern 'book'",
            expected_output="runtime contract has extra columns: books, games",
        ),
        DynamicColumnRejectionE2ETestCase(
            description="an unsupported look-around name pattern is a compile error",
            name_pattern_entry=",\n      name_pattern '(?=books)books'",
            expected_output="has invalid name_pattern: look-around",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dynamic_name_pattern_when_building_then_mismatches_and_unsupported_patterns_fail(
    test_case: DynamicColumnRejectionE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = dynamic_category_project(
        tmp_path=tmp_path, name_pattern_entry=test_case.name_pattern_entry
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_returncode, output
    assert test_case.expected_output in output, output
