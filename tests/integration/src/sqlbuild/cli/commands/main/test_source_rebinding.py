"""Integration coverage for rebinding models to inspected expression-source columns."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import SourceRebindingTestCase
from tests.integration.src.sqlbuild.cli.commands.main.helpers import (
    execute_duckdb_sql,
    record_source_rebinding_analyses,
    write_expression_source_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceRebindingTestCase(
            description="names already known at compile time add no rebinding",
            source_expression="(SELECT 1 AS order_id, 'open' AS status)",
            model_sql=(
                "MODEL (materialized table);\n"
                'SELECT o.order_id, o.status FROM __source("typed_orders") AS o\n'
            ),
            expected_exit_code=0,
            expected_rebinding=False,
        ),
        SourceRebindingTestCase(
            description="names hidden from compile rebind and reject a missing column",
            source_expression="(SELECT * FROM main.raw_orders)",
            model_sql=(
                'MODEL (materialized table);\nSELECT o.missing FROM __source("typed_orders") AS o\n'
            ),
            expected_exit_code=1,
            expected_rebinding=True,
            expected_fragment="error[B002]",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_expression_source_when_planning_then_rebinds_only_on_new_column_evidence(
    test_case: SourceRebindingTestCase,
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
        source_expression=test_case.source_expression,
        model_sql=test_case.model_sql,
    )
    analysed: list[str] = record_source_rebinding_analyses(monkeypatch)
    _ = capsys.readouterr()

    exit_code: int = main(["--project-dir", str(tmp_path), "--no-color", "plan"])

    output: str = "".join(capsys.readouterr())
    assert exit_code == test_case.expected_exit_code, output
    assert test_case.expected_fragment in output
    assert bool(analysed) is test_case.expected_rebinding


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
