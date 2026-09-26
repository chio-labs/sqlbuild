"""Real compiler and CLI coverage for transactional Rule fixes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    FormatCompileIntegrationTestCase,
    SemanticFixTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [FormatCompileIntegrationTestCase("bare union", "UNION DISTINCT")],
    ids=lambda case: case.description,
)
def test_given_bare_union_when_fixing_then_preserves_output_and_is_idempotent(
    test_case: FormatCompileIntegrationTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "duckdb"\n')
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    original = 'MODEL (description "Orders");\nSELECT 1 AS order_id UNION SELECT 2 AS order_id\n'
    model.write_text(original)
    assert main(["--project-dir", str(tmp_path), "format", "--fix", "--check", "--json"]) == 1
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert model.read_text() == original
    assert any(
        fix["code"] == "SQBRSQL008" and fix["status"] == "applied" for fix in payload["rule_fixes"]
    )
    assert main(["--project-dir", str(tmp_path), "format", "--fix", "--json"]) == 0
    capsys.readouterr()
    assert test_case.expected_literal in model.read_text()
    assert main(["--project-dir", str(tmp_path), "format", "--fix", "--check", "--json"]) == 0


@pytest.mark.parametrize(
    "test_case",
    [FormatCompileIntegrationTestCase("null comparison", "= NULL")],
    ids=lambda case: case.description,
)
def test_given_null_comparison_when_fixing_then_refuses_semantics_change(
    test_case: FormatCompileIntegrationTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "duckdb"\n')
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text('MODEL (description "Orders");\nSELECT 1 AS order_id WHERE 1 = NULL\n')
    main(["--project-dir", str(tmp_path), "format", "--fix", "--json"])
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert any(
        fix["code"] == "SQBRSQL001" and fix["status"] == "refused" for fix in payload["rule_fixes"]
    )
    assert test_case.expected_literal in model.read_text()


@pytest.mark.parametrize(
    "test_case",
    [FormatCompileIntegrationTestCase("unanalysed model", "format-fix-verification-failed")],
    ids=lambda case: case.description,
)
def test_given_unanalysed_model_when_fixing_then_verification_preserves_original_file(
    test_case: FormatCompileIntegrationTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "duckdb"\n')
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "customers.sql").write_text(
        'MODEL (description "Customers");\nSELECT 1 AS customer_id\n'
    )
    model: Path = models / "orders.sql"
    original = (
        'MODEL (description "Orders", sql_analysis false);\n'
        "WITH unused AS (SELECT 2 AS customer_id) SELECT 1 AS order_id\n"
    )
    model.write_text(original)
    assert main(["--project-dir", str(tmp_path), "format", "--fix", "--json"]) == 1
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert model.read_text() == original
    assert any(v["code"] == test_case.expected_literal for v in payload["violations"])


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticFixTestCase(
            "comma product",
            "SELECT a.order_id, b.customer_id FROM "
            "(SELECT 1 AS order_id) AS a, (SELECT 2 AS customer_id) AS b",
            "SQBRSQL002",
        ),
        SemanticFixTestCase(
            "unused CTE",
            "WITH unused AS (SELECT 2 AS customer_id) SELECT 1 AS order_id",
            "SQBRSQL005",
        ),
        SemanticFixTestCase(
            "redundant distinct",
            "SELECT DISTINCT order_id FROM (SELECT 1 AS order_id) AS orders GROUP BY order_id",
            "SQBRSQL006",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_safe_native_fix_when_formatting_then_compiler_and_query_results_are_preserved(
    test_case: SemanticFixTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "duckdb"\n')
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text('MODEL (description "Orders", schema analytics);\n' + test_case.sql)
    assert main(["--project-dir", str(tmp_path), "format", "--fix", "--json"]) == 0
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert any(
        fix["code"] == test_case.expected_code and fix["status"] == "applied"
        for fix in payload["rule_fixes"]
    )
    with duckdb.connect() as connection:
        expected: list[tuple[Any, ...]] = connection.execute(test_case.sql).fetchall()
        actual: list[tuple[Any, ...]] = connection.execute(
            model.read_text().split(";", 1)[1]
        ).fetchall()
    assert actual == expected


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticFixTestCase(
            "Snowflake cartesian JOIN",
            "SELECT a.order_id, b.customer_id FROM "
            "(SELECT 1 AS order_id) AS a JOIN (SELECT 2 AS customer_id) AS b",
            "SQBRSQL003",
            dialect="snowflake",
        ),
        SemanticFixTestCase(
            "DuckDB invalid JOIN",
            "SELECT a.order_id, b.customer_id FROM "
            "(SELECT 1 AS order_id) AS a JOIN (SELECT 2 AS customer_id) AS b",
            "SQBRSQL003",
            expected_status="refused",
        ),
        SemanticFixTestCase(
            "parentheses precedence",
            "SELECT DISTINCT (1 + 2) * 3 AS order_id",
            "SQBRSQL013",
            expected_status="refused",
        ),
        SemanticFixTestCase(
            "boolean CASE",
            "SELECT CASE WHEN 1 = 2 THEN TRUE ELSE FALSE END AS active",
            "SQBRSQL030",
            expected_status="refused",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dialect_sensitive_rewrite_when_fixing_then_requires_semantic_proof(
    test_case: SemanticFixTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        f'name = "orders"\nadapter = "{test_case.dialect}"\n'
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders", database example, schema analytics);\n' + test_case.sql
    )
    assert main(["--project-dir", str(tmp_path), "format", "--fix", "--json"]) == 0
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert any(
        fix["code"] == test_case.expected_code and fix["status"] == test_case.expected_status
        for fix in payload["rule_fixes"]
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
