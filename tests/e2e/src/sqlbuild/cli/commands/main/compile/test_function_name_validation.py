"""E2E tests for compile-time rejection of built-in spellings the target dialect lacks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    FunctionNameCompileTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_STARTS_WITH_FUNCTION: str = (
    "FUNCTION (\n"
    "  arguments (value STRING, prefix STRING),\n"
    "  returns BOOLEAN,\n"
    "  database warehouse,\n"
    "  schema analytics,\n"
    ");\n\n"
    "LEFT(value, LENGTH(prefix)) = prefix\n"
)

_SNOWFLAKE_PROJECT: str = 'name = "products"\nadapter = "snowflake"\n'
_DUCKDB_PROJECT: str = (
    'name = "products"\nadapter = "duckdb"\n\n[connection]\ndatabase = ":memory:"\n'
)


@pytest.mark.parametrize(
    "test_case",
    (
        FunctionNameCompileTestCase(
            description="snowflake STARTS_WITH is rejected with the Snowflake spelling",
            project_toml=_SNOWFLAKE_PROJECT,
            projection_sql="    STARTS_WITH(product_name, 'a') AS is_featured",
            expected_exit_code=1,
            expected_diagnostics=(
                (
                    "B101",
                    "Unknown function 'STARTS_WITH' for dialect Snowflake; did you mean STARTSWITH?",
                    4,
                    5,
                ),
            ),
        ),
        FunctionNameCompileTestCase(
            description="snowflake accepted spellings and an alias-named UDF compile",
            project_toml=_SNOWFLAKE_PROJECT,
            projection_sql=(
                "    STARTSWITH(product_name, 'a') AS is_featured,\n"
                "    SUBSTR(product_name, 1, 2) AS short_name,\n"
                "    TIMESTAMPDIFF(day, '2026-01-01'::date, '2026-01-02'::date) AS age_days,\n"
                "    TRY_TO_DECIMAL('1.25', 10, 2) AS unit_price,\n"
                "    __udf(\"starts_with\")(product_name, 'a') AS has_prefix"
            ),
            expected_exit_code=0,
            expected_diagnostics=(),
        ),
        FunctionNameCompileTestCase(
            description="duckdb STARTSWITH is rejected with the DuckDB spelling",
            project_toml=_DUCKDB_PROJECT,
            projection_sql="    STARTSWITH(product_name, 'a') AS is_featured",
            expected_exit_code=1,
            expected_diagnostics=(
                (
                    "B101",
                    "Unknown function 'STARTSWITH' for dialect DuckDB; did you mean STARTS_WITH?",
                    4,
                    5,
                ),
            ),
        ),
        FunctionNameCompileTestCase(
            description="duckdb catalogue spellings compile",
            project_toml=_DUCKDB_PROJECT,
            projection_sql=(
                "    starts_with(product_name, 'a') AS is_featured,\n"
                "    prefix(product_name, 'a') AS has_prefix,\n"
                "    substr(product_name, 1, 2) AS short_name"
            ),
            expected_exit_code=0,
            expected_diagnostics=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_builtin_spelling_when_compiling_then_dialect_support_is_enforced(
    test_case: FunctionNameCompileTestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="products",
        repo_files={
            "sqlbuild_project.toml": test_case.project_toml,
            "functions/sql/starts_with.sql": _STARTS_WITH_FUNCTION,
            "models/products.sql": (
                "MODEL (database warehouse, schema analytics);\n\n"
                "SELECT\n"
                f"{test_case.projection_sql}\n"
                "FROM (SELECT 'anvil' AS product_name) AS catalog_items\n"
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        project_dir=project_dir, command=("compile", "--json", "--no-cache")
    )

    payload: dict[str, object] = json.loads(result.stdout)
    diagnostics: list[dict[str, object]] = cast(list[dict[str, object]], payload["diagnostics"])
    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert (
        tuple((item["code"], item["message"], item["line"], item["column"]) for item in diagnostics)
        == test_case.expected_diagnostics
    )
