"""E2E coverage of outer casts that establish a contract type, compared as the dialect does."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    ContractCastTypeTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_PROJECT_TOML: str = (
    'name = "shop"\nadapter = "snowflake"\ndefault_target = "dev"\n\n'
    '[targets.dev]\ndatabase = "warehouse"\nschema = "analytics"\n\n'
    '[scopes]\nenforce_placement = false\n\n[rules]\nselect = ["SQBRCONTRACT105"]\n'
)
_STATUS_LABEL_MACRO: str = (
    "MACRO (\n"
    '  description "Map a status code to a label.",\n'
    "  arguments (code VARCHAR),\n"
    "  returns VARCHAR,\n"
    ");\n\n"
    "CASE @code WHEN 'a' THEN 'ACTIVE' WHEN 'c' THEN 'CLOSED' END\n"
)
_ORDERS_MODEL: str = (
    'MODEL (description "Orders.");\n\n'
    "SELECT CAST(1 AS INTEGER) AS order_id, CAST('a' AS VARCHAR) AS code\n"
)
_LABELS_MODEL: str = (
    "MODEL (\n"
    '  description "Order status labels.",\n'
    "  contract enforced,\n"
    "  columns (\n"
    "    order_id (type INTEGER),\n"
    "    status_label (type VARCHAR),\n"
    "  ),\n"
    ");\n\n"
    "SELECT\n"
    "  o.order_id,\n"
    "  {projection} AS status_label\n"
    'FROM __ref("orders") AS o\n'
    "WHERE o.order_id > 0\n"
)


@pytest.mark.parametrize(
    "test_case",
    [
        ContractCastTypeTestCase(
            description="a cast to the maximum VARCHAR length is the declared VARCHAR",
            projection="CAST(@sql.status_label(o.code) AS VARCHAR(16777216))",
            expected_exit_code=0,
            expected_fragments=("0 errors",),
        ),
        ContractCastTypeTestCase(
            description="a cast to STRING is the declared VARCHAR",
            projection="CAST(@sql.status_label(o.code) AS STRING)",
            expected_exit_code=0,
            expected_fragments=("0 errors",),
        ),
        ContractCastTypeTestCase(
            description="a narrower cast names both types, points at the cast and asks to change it",
            projection="CAST(@sql.status_label(o.code) AS VARCHAR(10))",
            expected_exit_code=1,
            expected_fragments=(
                'error[SQBRCONTRACT105]: output "status_label" has an outer cast to VARCHAR(10),'
                " which is not its declared contract type VARCHAR",
                "--> models/labels.sql:12:3",
                "help: Change the outer cast to CAST(... AS VARCHAR).",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_outer_cast_on_contract_output_when_compiling_then_types_compare_as_snowflake_does(
    test_case: ContractCastTypeTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="shop",
        repo_files={
            "sqlbuild_project.toml": _PROJECT_TOML,
            "macros/sql/status_label.sql": _STATUS_LABEL_MACRO,
            "models/orders.sql": _ORDERS_MODEL,
            "models/labels.sql": _LABELS_MODEL.format(projection=test_case.projection),
        },
    )

    compiled: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("--no-color", "compile")
    )
    report: str = compiled.stdout + compiled.stderr

    assert compiled.returncode == test_case.expected_exit_code, report
    assert [fragment in report for fragment in test_case.expected_fragments] == [
        True for _ in test_case.expected_fragments
    ], report
