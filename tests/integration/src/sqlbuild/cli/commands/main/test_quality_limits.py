"""Project-wide SQL quality limits through the real compiler."""

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    LiteralLimitTestCase,
    OverridePolicyTestCase,
    RankingLimitTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RankingLimitTestCase("row number", "ROW_NUMBER() OVER (ORDER BY a, b)", 1, 1),
        RankingLimitTestCase("rank", "RANK() OVER (ORDER BY a, b)", 1, 1),
        RankingLimitTestCase("dense rank", "DENSE_RANK() OVER (ORDER BY a, b)", 1, 1),
        RankingLimitTestCase("first value", "FIRST_VALUE(a) OVER (ORDER BY a, b)", 1, 1),
        RankingLimitTestCase("last value", "LAST_VALUE(a) OVER (ORDER BY a, b)", 1, 1),
        RankingLimitTestCase("at cap", "ROW_NUMBER() OVER (ORDER BY a, b)", 2, 0),
        RankingLimitTestCase("non-ranking", "SUM(a) OVER (ORDER BY a, b)", 1, 0),
        RankingLimitTestCase(
            "one compound expression", "RANK() OVER (ORDER BY COALESCE(a, b))", 1, 0
        ),
        RankingLimitTestCase("named window", "RANK() OVER W", 1, 1, " WINDOW w AS (ORDER BY a, b)"),
        RankingLimitTestCase(
            "qualify", "a", 1, 1, " QUALIFY ROW_NUMBER() OVER (ORDER BY a, b) = 1"
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ranking_limit_when_compiling_then_enforces_expression_count(
    test_case: RankingLimitTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = ["SQBRSQL043"]\n'
        f"max_ranking_order_by = {test_case.limit}\n"
    )
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "orders.sql").write_text(
        'MODEL (description "Orders");\nWITH items AS (SELECT 1 AS a, 2 AS b) '
        f"SELECT {test_case.expression} AS result FROM items{test_case.suffix}"
    )
    assert (
        main(["--project-dir", str(tmp_path), "compile", "--json"]) == test_case.expected_exit_code
    )
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert any(item["code"] == "SQBRSQL043" for item in payload["diagnostics"]) == bool(
        test_case.expected_exit_code
    )


@pytest.mark.parametrize(
    "test_case",
    [
        OverridePolicyTestCase(
            "default permits model opt-out",
            "",
            "MODEL (sql_analysis false); SELECT 1 AS order_id",
            0,
            "",
        ),
        OverridePolicyTestCase(
            "closed policy rejects model opt-out without selected Rules",
            "allow_model_overrides = false",
            "MODEL (sql_analysis false); SELECT 1 AS order_id",
            1,
            "MODEL (sql_analysis false)",
        ),
        OverridePolicyTestCase(
            "closed policy rejects inline directive",
            "allow_model_overrides = false",
            "MODEL ();\n-- sqb: ignore SQBRSQL001 because example\nSELECT 1 AS order_id",
            1,
            "Inline suppression 'SQBRSQL001'",
        ),
        OverridePolicyTestCase(
            "closed policy accepts compliant model",
            "allow_model_overrides = false",
            "MODEL (); SELECT 1 AS order_id",
            0,
            "",
        ),
        OverridePolicyTestCase(
            "closed policy rejects path ignore",
            'allow_model_overrides = false\n[[rules.rule_ignores]]\nrules = ["SQBRSQL001"]\npaths = ["models/**"]\nreason = "example"',
            "MODEL (); SELECT 1 AS order_id",
            1,
            "rules.rule_ignores",
        ),
        OverridePolicyTestCase(
            "closed policy rejects exact exemption",
            'allow_model_overrides = false\n[[rules.rule_exceptions]]\nrule = "SQBRSQL001"\npath = "models/orders.sql"\nreason = "example"',
            "MODEL (); SELECT 1 AS order_id",
            1,
            "rules.rule_exceptions",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_override_policy_when_compiling_then_local_opt_outs_are_enforced(
    test_case: OverridePolicyTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\n' + test_case.configuration + "\n"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(test_case.sql)
    assert (
        main(["--project-dir", str(tmp_path), "compile", "--json"]) == test_case.expected_exit_code
    )
    captured: CaptureResult[str] = capsys.readouterr()
    assert test_case.expected_message in captured.out + captured.err


@pytest.mark.parametrize(
    "test_case",
    [
        LiteralLimitTestCase("split at spaces", "'pending shipped returned'", 10, "applied", 0),
        LiteralLimitTestCase(
            "regex alternation", "'^(PENDING|SHIPPED|RETURNED)$'", 12, "applied", 0
        ),
        LiteralLimitTestCase("doubled quote", "'pending customer''s shipment'", 10, "refused", 1),
        LiteralLimitTestCase("escape sequence", "'pending\\d shipped returned'", 10, "refused", 1),
        LiteralLimitTestCase("no split boundary", "'abcdefghijklmnop'", 10, "refused", 1),
        LiteralLimitTestCase("typed literal", "DATE '2026-01-01'", 8, "refused", 1),
    ],
    ids=lambda case: case.description,
)
def test_given_long_literal_when_fixing_then_preserves_values_or_refuses_with_reason(
    test_case: LiteralLimitTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = ["SQBRSQL044"]\n'
        f"max_literal_length = {test_case.limit}\n"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(f"MODEL (); SELECT {test_case.literal} AS status")
    assert main(["--project-dir", str(tmp_path), "compile", "--json"]) == 1
    before: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert any(item["code"] == "SQBRSQL044" for item in before["diagnostics"])
    assert main(["--project-dir", str(tmp_path), "format", "--fix", "--json"]) == 0
    fixed: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert any(
        item["code"] == "SQBRSQL044" and item["status"] == test_case.expected_status
        for item in fixed["rule_fixes"]
    )
    assert (
        main(["--project-dir", str(tmp_path), "compile", "--json"])
        == test_case.expected_compile_exit
    )
    with duckdb.connect() as connection:
        expected: list[tuple[Any, ...]] = connection.execute(
            f"SELECT {test_case.literal}"
        ).fetchall()
        actual: list[tuple[Any, ...]] = connection.execute(
            model.read_text().split(";", 1)[1]
        ).fetchall()
    assert actual == expected


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
