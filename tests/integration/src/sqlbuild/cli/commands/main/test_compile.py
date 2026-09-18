"""Integration coverage for compiler SQL dialect support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    ContractNullabilityCompileIntegrationTestCase,
    ProjectDirectoryCompileIntegrationTestCase,
    SnowflakeCompileIntegrationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeCompileIntegrationTestCase(
            description="grouping sets include a nested variant dynamic key",
            query_sql="""WITH orders AS (
    SELECT
        'ready' AS category,
        OBJECT_CONSTRUCT('labels', OBJECT_CONSTRUCT('1', 'priority')) AS attributes,
        1 AS item_id,
        10 AS amount
)
SELECT
    category,
    attributes:labels[TO_VARCHAR(item_id)] AS attribute_value,
    SUM(amount) AS total_amount
FROM orders
GROUP BY GROUPING SETS (
    (category, attributes:labels[TO_VARCHAR(item_id)]),
    ()
)
""",
            expected_exit_code=0,
            expected_diagnostics=(),
            expected_query_fragment="attributes:labels[TO_VARCHAR(item_id)]",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_supported_snowflake_aggregation_when_compiling_then_project_succeeds(
    test_case: SnowflakeCompileIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "snowflake"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "order_summary.sql"
    model.parent.mkdir()
    model.write_text(
        f"MODEL (database warehouse, schema analytics);\n\n{test_case.query_sql}",
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    result: dict[str, object] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, object]] = cast(list[dict[str, object]], result["diagnostics"])
    resources: dict[str, object] = cast(dict[str, object], result["resources"])
    models: list[dict[str, object]] = cast(list[dict[str, object]], resources["models"])

    assert exit_code == test_case.expected_exit_code
    assert tuple(item["code"] for item in diagnostics) == test_case.expected_diagnostics
    assert test_case.expected_query_fragment in cast(str, models[0]["query_sql"])


@pytest.mark.parametrize(
    "test_case",
    (
        ContractNullabilityCompileIntegrationTestCase(
            description="not null audit remains runtime only",
            column_sql="order_id (type INTEGER, audits [not_null])",
            expected_exit_code=0,
            expected_diagnostics=(),
        ),
        ContractNullabilityCompileIntegrationTestCase(
            description="nullable false remains a schema contract",
            column_sql="order_id (type INTEGER, nullable false)",
            expected_exit_code=1,
            expected_diagnostics=("K004",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_nullable_output_when_compiling_contract_then_only_schema_nullability_fails(
    test_case: ContractNullabilityCompileIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        "MODEL (\n"
        "  contract enforced,\n"
        f"  columns ({test_case.column_sql}),\n"
        ");\n\n"
        "SELECT CAST(NULL AS INTEGER) AS order_id\n",
        encoding="utf-8",
    )
    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    result: dict[str, object] = json.loads(capsys.readouterr().out)
    diagnostics: list[dict[str, object]] = cast(list[dict[str, object]], result["diagnostics"])

    assert exit_code == test_case.expected_exit_code
    assert tuple(item["code"] for item in diagnostics) == test_case.expected_diagnostics


@pytest.mark.parametrize(
    "test_case",
    (
        ProjectDirectoryCompileIntegrationTestCase(
            description="relative project directory preserves private macro scope",
            expected_exit_code=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_relative_project_directory_when_compiling_then_private_macro_is_visible(
    test_case: ProjectDirectoryCompileIntegrationTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project_dir: Path = tmp_path / "project"
    (project_dir / "models" / "orders" / "_sqlbuild" / "_macros").mkdir(parents=True)
    (project_dir / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    (project_dir / "models" / "orders" / "_sqlbuild" / "_macros" / "order_id.py").write_text(
        'def order_id() -> str:\n    return "CAST(1 AS INTEGER)"\n', encoding="utf-8"
    )
    (project_dir / "models" / "orders" / "orders.sql").write_text(
        "MODEL (materialized table);\nSELECT @order_id() AS order_id\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    exit_code: int = main(["--project-dir", project_dir.name, "compile", "--json", "--no-cache"])
    result: dict[str, object] = json.loads(capsys.readouterr().out)
    summary: dict[str, object] = cast(dict[str, object], result["summary"])

    assert exit_code == test_case.expected_exit_code
    assert summary["errors"] == 0
    assert summary["models"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
