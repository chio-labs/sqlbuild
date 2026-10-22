"""Real-CLI coverage of side-only example rows in unkeyed diffs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.diff._test_types import (
    UnkeyedExamplesE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.diff.helpers import (
    build_both_environments,
    execute_duckdb,
    prepare_diff_project,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        UnkeyedExamplesE2ETestCase(
            description="model diff shows the dropped row and the duplicated row",
            mutation_sql=(
                "DELETE FROM dev.orders_snapshot WHERE order_id = 1",
                "INSERT INTO dev.orders_snapshot SELECT * FROM dev.orders_snapshot WHERE order_id = 2",
            ),
            command=(
                "diff",
                "prod:dev",
                "--full",
                "--unkeyed",
                "--select",
                "orders_snapshot",
                "--exclude-column",
                "status",
            ),
            expected_from_order_ids=(1,),
            expected_to_order_ids=(2,),
            expected_truncated=False,
        ),
        UnkeyedExamplesE2ETestCase(
            description="query diff bounds examples by max-row-only-examples",
            mutation_sql=(),
            command=(
                "diff",
                "--left-query",
                "SELECT * FROM (VALUES (1), (1), (1), (2)) AS orders(order_id)",
                "--right-query",
                "SELECT * FROM (VALUES (2)) AS orders(order_id)",
                "--unkeyed",
                "--max-row-only-examples",
                "2",
            ),
            expected_from_order_ids=(1, 1),
            expected_to_order_ids=(),
            expected_truncated=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_side_only_rows_when_diffing_unkeyed_then_json_shows_bounded_full_rows(
    test_case: UnkeyedExamplesE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_diff_project(tmp_path)
    build_both_environments(project_dir=project_dir)
    for mutation_sql in test_case.mutation_sql:
        execute_duckdb(db_path=project_dir / "diff.duckdb", sql=mutation_sql)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(*test_case.command, "--json"), project_dir=project_dir
    )

    assert result.returncode == 1, result.stdout + result.stderr
    (model,) = json.loads(result.stdout)["models"]
    examples: dict[str, Any] = model["examples"]

    def order_ids(rows: list[dict[str, Any]]) -> tuple[int, ...]:
        return tuple(row["order_id"] for row in rows)

    assert examples["from_only_keys"] == []
    assert examples["to_only_keys"] == []
    assert order_ids(examples["from_only_rows"]) == test_case.expected_from_order_ids
    assert order_ids(examples["to_only_rows"]) == test_case.expected_to_order_ids
    assert examples["truncated_by_count"] is test_case.expected_truncated


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
