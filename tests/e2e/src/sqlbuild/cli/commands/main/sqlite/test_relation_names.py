from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.sqlite._test_types import (
    SqliteCollisionE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.sqlite.helpers import (
    MAIN_STAGING_ORDERS_FILES,
    SQLITE_FILE,
    STAGING_ORDERS_FILES,
    sqlite_rows,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_COLLISION_FRAGMENTS: tuple[str, ...] = (
    "error[A706]",
    "'staging.orders' and 'main.staging__orders'",
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteCollisionE2ETestCase(
            description="adding main staging__orders beside staging.orders is refused unbuilt",
            first_files=STAGING_ORDERS_FILES,
            second_files=MAIN_STAGING_ORDERS_FILES,
            expected_fragments=_COLLISION_FRAGMENTS,
            expected_tables=(("staging__orders",),),
            expected_rows=((1,),),
        ),
        SqliteCollisionE2ETestCase(
            description="adding staging.orders beside main staging__orders is refused unbuilt",
            first_files=MAIN_STAGING_ORDERS_FILES,
            second_files=STAGING_ORDERS_FILES,
            expected_fragments=_COLLISION_FRAGMENTS,
            expected_tables=(("staging__orders",),),
            expected_rows=((2,),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_colliding_relation_names_when_building_then_sqlite_refuses_before_writing(
    tmp_path: Path, test_case: SqliteCollisionE2ETestCase
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="staging_shop", repo_files=test_case.first_files
    )
    first: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    prepare_inline_project(
        tmp_path=tmp_path, project_name="staging_shop", repo_files=test_case.second_files
    )

    second: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode != 0, second.stdout + second.stderr
    output: str = second.stdout + second.stderr
    assert all(fragment in output for fragment in test_case.expected_fragments), output
    assert (
        sqlite_rows(
            db_path=project_dir / SQLITE_FILE,
            sql="SELECT name FROM sqlite_schema WHERE type = 'table' AND name LIKE 'staging%orders'",
        )
        == test_case.expected_tables
    )
    assert (
        sqlite_rows(db_path=project_dir / SQLITE_FILE, sql="SELECT * FROM staging__orders")
        == test_case.expected_rows
    )
