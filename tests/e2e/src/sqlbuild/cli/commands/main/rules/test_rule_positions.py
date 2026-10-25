"""E2E coverage that model rule findings point at file lines and columns, not query ones."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.rules._test_types import RulePositionE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_HEADER: str = 'MODEL (description "Test model orders.", materialized table);'


@pytest.mark.parametrize(
    "test_case",
    [
        RulePositionE2ETestCase(
            description="a query on the header's line is offset by the header",
            model_sql=f"{_HEADER} WITH o AS (SELECT 1 AS id) SELECT * FROM o\n",
            expected_location="models/orders.sql:1:97 [SQBRMODEL102]",
        ),
        RulePositionE2ETestCase(
            description="a query starting on the header's line keeps later lines unshifted",
            model_sql=f"{_HEADER}   WITH o AS (SELECT 1 AS id)\nSELECT * FROM o\n",
            expected_location="models/orders.sql:2:8 [SQBRMODEL102]",
        ),
        RulePositionE2ETestCase(
            description="a query below the header counts file lines",
            model_sql=f"{_HEADER}\n-- orders\nWITH o AS (SELECT 1 AS id) SELECT * FROM o\n",
            expected_location="models/orders.sql:3:35 [SQBRMODEL102]",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_query_layout_when_running_rules_then_findings_use_file_positions(
    test_case: RulePositionE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="shop",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "shop"\nadapter = "duckdb"\n\n[connection]\ndatabase = "shop.duckdb"\n\n'
                "[scopes]\nenforce_placement = false\n"
            ),
            "models/orders.sql": test_case.model_sql,
        },
    )

    ran: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "rules", "run", "SQBRMODEL102"), project_dir=project_dir
    )

    assert test_case.expected_location in ran.stdout + ran.stderr, ran.stdout + ran.stderr
