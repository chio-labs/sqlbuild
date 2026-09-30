"""CLI e2e coverage for the missing_migration_origin target policy."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.refactor._test_types import (
    MissingOriginE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.refactor.helpers import (
    declare_missing_column_origin,
    order_history_files,
    project_toml,
    relation_columns,
    relation_type,
    sqb,
    write_orders_project,
)

_DENY: str = 'missing_migration_origin = "deny"\n'
_CONFIRM: str = 'missing_migration_origin = "require_confirmation"\n'


@pytest.mark.parametrize(
    "test_case",
    [
        MissingOriginE2ETestCase(
            description="fresh target builds with a warning by default",
            target_settings="",
            build_args=(),
            expected_exit=0,
            expected_output="migrate_from origin analytics.stg_orders does not exist",
            expected_relation_type="VIEW",
        ),
        MissingOriginE2ETestCase(
            description="deny stops the build",
            target_settings=_DENY,
            build_args=(),
            expected_exit=1,
            expected_output="error[M102]",
            expected_relation_type=None,
        ),
        MissingOriginE2ETestCase(
            description="require_confirmation stops an unconfirmed build",
            target_settings=_CONFIRM,
            build_args=(),
            expected_exit=1,
            expected_output="--allow-missing-migration-origin",
            expected_relation_type=None,
        ),
        MissingOriginE2ETestCase(
            description="require_confirmation builds once confirmed",
            target_settings=_CONFIRM,
            build_args=("--allow-missing-migration-origin",),
            expected_exit=0,
            expected_output="does not exist in this target",
            expected_relation_type="VIEW",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_model_on_fresh_target_when_building_then_policy_decides(
    tmp_path: Path, test_case: MissingOriginE2ETestCase
) -> None:
    """A rename's migrate_from finds no old relation on a target that never built it."""

    project_dir: Path = write_orders_project(
        tmp_path=tmp_path,
        files={"sqlbuild_project.toml": project_toml(target_settings=test_case.target_settings)},
    )

    renamed: subprocess.CompletedProcess[str] = sqb(
        project_dir, "rename", "model:stg_orders", "stg_order_lines"
    )
    built: subprocess.CompletedProcess[str] = sqb(project_dir, "build", *test_case.build_args)

    assert renamed.returncode == 0, renamed.stdout + renamed.stderr
    assert built.returncode == test_case.expected_exit, built.stdout + built.stderr
    assert test_case.expected_output in built.stdout + built.stderr
    assert (
        relation_type(project_dir=project_dir, name="stg_order_lines")
        == test_case.expected_relation_type
    )


@pytest.mark.parametrize(
    "test_case",
    [
        MissingOriginE2ETestCase(
            description="missing origin column is allowed by default",
            target_settings="",
            build_args=(),
            expected_exit=0,
            expected_output="column gross_amount does not exist",
            expected_relation_type="BASE TABLE",
            expected_columns=("order_id", "amount", "order_date", "revenue"),
        ),
        MissingOriginE2ETestCase(
            description="missing origin column stops the build under deny",
            target_settings=_DENY,
            build_args=(),
            expected_exit=1,
            expected_output="error[M109]",
            expected_relation_type="BASE TABLE",
            expected_columns=("order_id", "amount", "order_date"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_origin_column_when_building_then_policy_decides(
    tmp_path: Path, test_case: MissingOriginE2ETestCase
) -> None:
    """A column migrate_from naming a column the table never had follows the same policy."""

    project_dir: Path = write_orders_project(
        tmp_path=tmp_path,
        files={
            **order_history_files(materialized="incremental", udf=False),
            "sqlbuild_project.toml": project_toml(target_settings=test_case.target_settings),
        },
    )
    first: subprocess.CompletedProcess[str] = sqb(project_dir, "build")
    declare_missing_column_origin(project_dir=project_dir)

    built: subprocess.CompletedProcess[str] = sqb(project_dir, "build")

    assert first.returncode == 0, first.stdout + first.stderr
    assert built.returncode == test_case.expected_exit, built.stdout + built.stderr
    assert test_case.expected_output in built.stdout + built.stderr
    assert relation_columns(project_dir=project_dir, name="order_history") == (
        test_case.expected_columns
    )
