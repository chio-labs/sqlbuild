"""E2E regression tests for incremental relations dropped outside SQLBuild."""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    DroppedIncrementalRelationE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    dropped_incremental_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DroppedIncrementalRelationE2ETestCase(
            description="delete insert",
            incremental_strategy="delete_insert",
            expected_rows=(
                (2, "2026-01-02 01:00:00"),
                (3, "2026-01-03 01:00:00"),
                (4, "2026-01-04 01:00:00"),
            ),
        ),
        DroppedIncrementalRelationE2ETestCase(
            description="append",
            incremental_strategy="append",
            expected_rows=(
                (2, "2026-01-02 01:00:00"),
                (3, "2026-01-03 01:00:00"),
                (4, "2026-01-04 01:00:00"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_incremental_table_dropped_outside_sqlbuild_when_planning_and_building_then_recreates(
    tmp_path: Path,
    test_case: DroppedIncrementalRelationE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="dropped_orders",
        repo_files=dropped_incremental_project_files(
            incremental_strategy=test_case.incremental_strategy
        ),
    )
    db_path: Path = project_dir / "dropped_orders.duckdb"
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE TABLE main.raw_orders (id INTEGER, ordered_at TIMESTAMP); "
            "INSERT INTO main.raw_orders VALUES "
            "(1, '2026-01-01 05:00:00'), (2, '2026-01-02 01:00:00'), "
            "(3, '2026-01-03 01:00:00')"
        ),
    )
    first_build: CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first_build.returncode == 0, first_build.stdout + first_build.stderr
    execute_duckdb(
        db_path=db_path,
        sql=(
            "DROP TABLE main.orders; INSERT INTO main.raw_orders VALUES (4, '2026-01-04 01:00:00')"
        ),
    )

    plan: CompletedProcess[str] = run_sqb(command=("plan", "--json"), project_dir=project_dir)
    rebuild: CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert plan.returncode == 0, plan.stdout + plan.stderr
    document: dict[str, object] = json.loads(plan.stdout)
    models: object = document["models"]
    assert isinstance(models, list)
    model: dict[str, object] = models[0]
    assert (model["name"], model["action"], model["reason"]) == (
        "orders",
        "create_table",
        "first_run",
    )
    assert model["built_version_present"] is False
    assert model["identity_status"] == "missing"
    assert model["cursor_bounds"] == {
        "start": "2026-01-02T00:00:00",
        "end": "2026-01-05T00:00:00",
    }
    assert document["warnings"] == [
        {
            "severity": "warning",
            "message": (
                "orders: SQLBuild state records a previous build, but the relation no longer "
                "exists in the warehouse. It may have been dropped outside SQLBuild; planning a "
                "first run to recreate it."
            ),
            "model_name": "orders",
            "code": "RECORDED_RELATION_MISSING",
        }
    ]
    assert rebuild.returncode == 0, rebuild.stdout + rebuild.stderr
    assert "RECORDED_RELATION_MISSING" not in rebuild.stdout
    assert "no longer exists in the warehouse" in rebuild.stdout + rebuild.stderr
    assert (
        tuple(
            query_duckdb(
                db_path=db_path,
                sql="SELECT id, CAST(ordered_at AS VARCHAR) FROM main.orders ORDER BY id",
            )
        )
        == test_case.expected_rows
    )
    assert (
        query_duckdb(
            db_path=db_path,
            sql=(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE 'orders\\_\\_%' ESCAPE '\\'"
            ),
        )
        == []
    )
