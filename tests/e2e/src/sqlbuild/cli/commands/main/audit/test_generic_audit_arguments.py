"""CLI e2e coverage: generic audit arguments the audit's SQL never reads fail the compile."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.audit._test_types import (
    GenericAuditArgumentE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_AUDIT_PATH: str = "audits/generic/unique_within_group.sql"
_UNIQUE_WITHIN_GROUP: str = (
    "AUDIT ();\n\n"
    "SELECT @group_columns, COUNT(DISTINCT @column) AS distinct_count\n"
    "FROM @relation\nWHERE @column IS NOT NULL\nGROUP BY @group_columns\n"
    "HAVING COUNT(DISTINCT @column) > 1\n"
)


def _orders_model(arguments: str) -> str:
    return (
        "MODEL (description 'Test model orders.',\n  materialized table,\n  columns (\n"
        f"    status (audits [unique_within_group ({arguments})]),\n  ),\n);\n\n"
        "SELECT 1 AS order_id, 'open' AS status, 'web' AS channel\n"
    )


@pytest.mark.parametrize(
    "test_case",
    (
        GenericAuditArgumentE2ETestCase(
            description="every argument read by the audit compiles",
            arguments='group_columns "channel"',
            expected_exit_code=0,
            expected_message=None,
        ),
        GenericAuditArgumentE2ETestCase(
            description="an argument the audit never reads names itself for removal",
            arguments='group_columns "channel", where_condition "channel = \'web\'"',
            expected_exit_code=1,
            expected_message=(
                "models/orders.sql audit 'unique_within_group' passes argument "
                "'where_condition', which the audit's SQL in "
                f"{_AUDIT_PATH} never uses; remove 'where_condition' from the attachment"
            ),
        ),
        GenericAuditArgumentE2ETestCase(
            description="a misspelt argument is reported as unused",
            arguments='group_columns "channel", group_column "channel"',
            expected_exit_code=1,
            expected_message="passes argument 'group_column', which the audit's SQL in",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_generic_audit_arguments_when_compiling_then_unused_arguments_fail(
    test_case: GenericAuditArgumentE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="audit_arguments",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "audit_arguments"\nadapter = "duckdb"\n\n'
                '[connection]\ndatabase = "audit_arguments.duckdb"\n'
            ),
            _AUDIT_PATH: _UNIQUE_WITHIN_GROUP,
            "models/orders.sql": _orders_model(test_case.arguments),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    if test_case.expected_message is not None:
        assert test_case.expected_message in result.stdout + result.stderr
