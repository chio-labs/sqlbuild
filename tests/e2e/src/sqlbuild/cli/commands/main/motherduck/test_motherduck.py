from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.motherduck._test_types import (
    MotherDuckBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.motherduck.helpers import (
    cleanup_motherduck_schema,
    fetch_motherduck_rows,
    prepare_motherduck_build_project,
    relation_name,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        MotherDuckBuildE2ETestCase(
            description="motherduck build creates expected table",
            command=("--no-color", "build"),
            expected_table_name="fact_orders",
            expected_row_count=2,
            expected_stdout_fragments=("Execution", "OK"),
        )
    ],
    ids=["motherduck build creates expected table"],
)
def test_given_motherduck_project_when_building_then_expected_table_exists(
    tmp_path: Path,
    test_case: MotherDuckBuildE2ETestCase,
) -> None:
    project_dir: Path
    schema_name: str
    project_dir, schema_name = prepare_motherduck_build_project(tmp_path=tmp_path)

    try:
        result: subprocess.CompletedProcess[str] = run_sqb(
            command=test_case.command,
            project_dir=project_dir,
        )

        assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
        fragment: str
        for fragment in test_case.expected_stdout_fragments:
            assert fragment in result.stdout
        rows: tuple[tuple[object, ...], ...] = fetch_motherduck_rows(
            schema_name=schema_name,
            sql=(
                "SELECT COUNT(*) FROM "
                f"{relation_name(schema_name=schema_name, name=test_case.expected_table_name)}"
            ),
        )
        assert rows[0][0] == test_case.expected_row_count
    finally:
        cleanup_motherduck_schema(schema_name=schema_name)
