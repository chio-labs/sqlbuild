"""E2E coverage for rejecting unknown MODEL header, model config layer, and source keys."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    ModelHeaderKeyCompileCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_PROJECT_TOML: str = 'name = "orders"\nadapter = "duckdb"\n'


@pytest.mark.parametrize(
    "test_case",
    [
        ModelHeaderKeyCompileCase(
            description="misspelled MODEL key",
            repo_files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "models/stg_orders.sql": "MODEL (materialized view);\n\nSELECT 1 AS order_id\n",
                "models/fct_orders.sql": (
                    'MODEL (\n  materialized table,\n  descripton "Orders fact.",\n);\n\n'
                    'SELECT order_id FROM __ref("stg_orders")\n'
                ),
            },
            expected_fragments=(
                "error[D002]",
                "models/fct_orders.sql:3' has unsupported keys: descripton",
                "did you mean 'description'?",
            ),
        ),
        ModelHeaderKeyCompileCase(
            description="misspelled path default key",
            repo_files={
                "sqlbuild_project.toml": (
                    _PROJECT_TOML + '\n[path_defaults.staging]\nmaterialised = "view"\n'
                ),
                "models/staging/stg_orders.sql": "MODEL ();\n\nSELECT 1 AS order_id\n",
            },
            expected_fragments=(
                "error[D001]",
                "path_defaults['staging'] contains unknown key(s): materialised",
                "did you mean 'materialized'?",
            ),
        ),
        ModelHeaderKeyCompileCase(
            description="misspelled source column key",
            repo_files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "sources/raw.yml": (
                    "sources:\n  - name: raw_orders\n    expression: SELECT 1 AS order_id\n"
                    "    columns:\n      - name: order_id\n        tpye: INTEGER\n"
                ),
                "models/stg_orders.sql": (
                    'MODEL ();\n\nSELECT order_id FROM __source("raw_orders")\n'
                ),
            },
            expected_fragments=(
                "error[D006]",
                "source column has unknown keys: tpye",
                "did you mean 'type'?",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_model_config_key_when_compiling_then_fails_naming_key_and_nearest_key(
    test_case: ModelHeaderKeyCompileCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="orders", repo_files=test_case.repo_files
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project_dir
    )

    output: str = result.stdout + result.stderr
    assert result.returncode != 0, output
    assert all(fragment in output for fragment in test_case.expected_fragments), output


@pytest.mark.parametrize(
    "test_case",
    [
        ModelHeaderKeyCompileCase(
            description="custom materialization values live under config",
            repo_files={
                "sqlbuild_project.toml": _PROJECT_TOML,
                "materializations/order_snapshot.py": (
                    "from sqlbuild.executor.custom.models import (\n"
                    "    MaterializationContext,\n    MaterializationResult,\n)\n\n\n"
                    "def materialize(ctx: MaterializationContext) -> MaterializationResult:\n"
                    "    return MaterializationResult(success=True)\n"
                ),
                "models/order_snapshot.sql": (
                    "MODEL (\n  materialized order_snapshot,\n"
                    "  config (retention_days 7, partition_column order_id),\n);\n\n"
                    "SELECT 1 AS order_id\n"
                ),
            },
            expected_fragments=("Project compiled  1 model",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_custom_materialization_config_block_when_compiling_then_arbitrary_keys_pass(
    test_case: ModelHeaderKeyCompileCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="orders", repo_files=test_case.repo_files
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project_dir
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert all(fragment in output for fragment in test_case.expected_fragments), output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
