"""A built model switching between table and view replaces the existing relation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    MaterializationTypeChangeTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import order_totals_model_sql
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)

_PROJECT_TOML: str = (
    'name = "orders"\nadapter = "duckdb"\n[connection]\ndatabase = "orders.duckdb"\n'
)
_MODEL_PATH: str = "models/order_totals.sql"


@pytest.mark.parametrize(
    "test_case",
    [
        MaterializationTypeChangeTestCase(
            description="table then view then table",
            materializations=("table", "view", "table"),
            expected_table_types=("BASE TABLE", "VIEW", "BASE TABLE"),
        ),
        MaterializationTypeChangeTestCase(
            description="view then table then view",
            materializations=("view", "table", "view"),
            expected_table_types=("VIEW", "BASE TABLE", "VIEW"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_built_model_when_materialization_changes_then_build_replaces_relation(
    test_case: MaterializationTypeChangeTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="orders_project",
        repo_files={"sqlbuild_project.toml": _PROJECT_TOML},
    )
    model_path: Path = project_dir / _MODEL_PATH
    model_path.parent.mkdir(parents=True, exist_ok=True)
    outcomes: list[tuple[int, str, list[tuple[Any, ...]]]] = []
    for materialized in test_case.materializations:
        _ = model_path.write_text(
            order_totals_model_sql(materialized=materialized), encoding="utf-8"
        )
        built: subprocess.CompletedProcess[str] = run_sqb(
            project_dir=project_dir, command=("--no-color", "build")
        )
        table_types: list[tuple[Any, ...]] = query_duckdb(
            db_path=project_dir / "orders.duckdb",
            sql="SELECT table_type FROM information_schema.tables WHERE table_name = 'order_totals'",
        )
        outcomes.append((built.returncode, built.stdout + built.stderr, table_types))
    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=project_dir / "orders.duckdb", sql="SELECT order_id, total_cents FROM order_totals"
    )

    assert [outcome[0] for outcome in outcomes] == [0] * len(test_case.materializations), (
        f"{test_case.description}: {[outcome[1] for outcome in outcomes]}"
    )
    assert tuple(outcome[2][0][0] for outcome in outcomes) == test_case.expected_table_types, (
        test_case.description
    )
    assert rows == [(1, 250)], test_case.description


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
