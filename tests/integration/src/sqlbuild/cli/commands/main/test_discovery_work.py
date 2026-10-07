"""Integration coverage for discovery work shared by compile, plan, and build."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import DiscoveryWorkTestCase
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    execute_duckdb_sql,
    record_eager_output_column_scans,
    write_expression_source_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DiscoveryWorkTestCase(
            description="compile",
            command=("compile",),
            expected_exit_code=0,
            expected_eager_output_column_scans=0,
        ),
        DiscoveryWorkTestCase(
            description="plan",
            command=("plan", "--json"),
            expected_exit_code=0,
            expected_eager_output_column_scans=0,
        ),
        DiscoveryWorkTestCase(
            description="build",
            command=("build",),
            expected_exit_code=0,
            expected_eager_output_column_scans=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_running_command_then_discovery_skips_eager_column_locations(
    test_case: DiscoveryWorkTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execute_duckdb_sql(
        db_path=tmp_path / "orders.duckdb",
        sql="CREATE TABLE raw_orders AS SELECT 1 AS order_id",
    )
    write_expression_source_project(
        project_dir=tmp_path,
        source_expression="(SELECT 1 AS order_id, 'open' AS status)",
        model_sql=(
            "MODEL (description 'Test model.', materialized table);\n"
            'SELECT o.order_id, o.status FROM __source("typed_orders") AS o\n'
        ),
    )
    scanned: list[dict[str, object]] = record_eager_output_column_scans(monkeypatch)
    _ = capsys.readouterr()

    exit_code: int = main(["--project-dir", str(tmp_path), "--no-color", *test_case.command])

    output: str = "".join(capsys.readouterr())
    assert exit_code == test_case.expected_exit_code, output
    assert len(scanned) == test_case.expected_eager_output_column_scans


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
