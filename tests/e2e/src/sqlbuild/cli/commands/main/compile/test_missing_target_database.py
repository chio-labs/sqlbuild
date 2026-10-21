"""CLI e2e coverage: the S101 missing-database error and its single settings example."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    MissingTargetDatabaseTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    (
        MissingTargetDatabaseTestCase(
            description="project defaults without a database",
            project_toml=(
                'name = "orders"\nadapter = "snowflake"\n\n[defaults]\nschema = "analytics"\n'
            ),
            expected_error=(
                "error[S101]: snowflake execution requires explicit target database. model "
                "'orders' resolved to database=None schema='analytics'. Set them in the model "
                "config, the environment config, or the project defaults.\n"
                "  = help: to set project-wide defaults, set this in sqlbuild_project.toml:\n"
                "            [defaults]\n"
                '            database = "my_database"\n'
            ),
            expected_example_count=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_snowflake_model_without_database_when_compiling_then_s101_shows_one_example(
    test_case: MissingTargetDatabaseTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="orders",
        repo_files={
            "sqlbuild_project.toml": test_case.project_toml,
            "models/orders.sql": (
                "MODEL (description 'Test model orders.', materialized view);\n\n"
                "SELECT 1 AS order_id\n"
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project_dir
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert test_case.expected_error in result.stderr
    assert result.stderr.count("[defaults]") == test_case.expected_example_count
