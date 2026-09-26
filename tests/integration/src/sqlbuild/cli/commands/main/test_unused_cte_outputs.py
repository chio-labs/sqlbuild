"""Unused CTE output enforcement and fixed-point fixes through the compiler CLI."""

import json
from pathlib import Path
from typing import Any

import duckdb
import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import CteOutputRuleTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        CteOutputRuleTestCase(
            "unused intermediate column",
            "WITH prepared AS (SELECT 1 AS a, 2 AS b), final AS (SELECT a FROM prepared) SELECT * FROM final",
            1,
            1,
        ),
        CteOutputRuleTestCase(
            "WHERE-only read",
            "WITH prepared AS (SELECT 1 AS a, 2 AS b), final AS (SELECT a FROM prepared WHERE b > 0) SELECT * FROM final",
            0,
            0,
        ),
        CteOutputRuleTestCase(
            "DISTINCT is a finding without a fix",
            "WITH prepared AS (SELECT DISTINCT 1 AS a, 2 AS b), final AS (SELECT a FROM prepared) SELECT * FROM final",
            1,
            0,
            1,
        ),
        CteOutputRuleTestCase(
            "set outputs are semantically required",
            "WITH prepared AS (SELECT 1 AS a, 2 AS b UNION ALL SELECT 3 AS a, 4 AS b), final AS (SELECT a FROM prepared) SELECT * FROM final",
            0,
            0,
        ),
        CteOutputRuleTestCase(
            "terminal CTE outputs",
            "WITH final AS (SELECT 1 AS a, 2 AS b) SELECT * FROM final",
            0,
            0,
        ),
        CteOutputRuleTestCase(
            "star pass-through fixed point",
            "WITH prepared AS (SELECT 1 AS a, 2 AS b), passed AS (SELECT * FROM prepared), final AS (SELECT a FROM passed) SELECT * FROM final",
            1,
            2,
        ),
        CteOutputRuleTestCase(
            "column removal exposes unreachable CTE",
            "WITH helper AS (SELECT 2 AS b), prepared AS (SELECT 1 AS a, (SELECT b FROM helper) AS b), final AS (SELECT a FROM prepared) SELECT * FROM final",
            1,
            2,
        ),
        CteOutputRuleTestCase(
            "ref import exemption",
            'WITH imported AS (SELECT * FROM __ref("input")), prepared AS (SELECT a, b FROM imported), final AS (SELECT a FROM prepared) SELECT * FROM final',
            1,
            1,
        ),
        CteOutputRuleTestCase(
            "source import exemption",
            'WITH imported AS (SELECT * FROM __source("input_source")), prepared AS (SELECT a, b FROM imported), final AS (SELECT a FROM prepared) SELECT * FROM final',
            1,
            1,
        ),
        CteOutputRuleTestCase(
            "seed import exemption",
            'WITH imported AS (SELECT * FROM __seed("input_seed")), prepared AS (SELECT a, b FROM imported), final AS (SELECT a FROM prepared) SELECT * FROM final',
            1,
            1,
        ),
        CteOutputRuleTestCase(
            "GROUP BY key retained",
            "WITH prepared AS (SELECT a, COUNT(*) AS n FROM (VALUES (1), (2)) AS items(a) GROUP BY a), final AS (SELECT n FROM prepared) SELECT * FROM final",
            1,
            1,
        ),
        CteOutputRuleTestCase(
            "local alias needs restructuring",
            "WITH prepared AS (SELECT 1 AS a, -a AS b ORDER BY b LIMIT 1), final AS (SELECT a FROM prepared) SELECT * FROM final",
            1,
            0,
            1,
        ),
        CteOutputRuleTestCase(
            "nested shadowed CTE outputs",
            "WITH prepared AS (SELECT 1 AS a, 2 AS b), nested AS (WITH prepared AS (SELECT 3 AS a, 4 AS b) SELECT a FROM prepared), final AS (SELECT prepared.a, nested.a AS c FROM prepared CROSS JOIN nested) SELECT * FROM final",
            2,
            2,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cte_output_usage_when_fixing_then_only_verified_unread_slots_are_removed(
    test_case: CteOutputRuleTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = ["SQBRSQL042", "SQBRSQL005"]\n'
    )
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "input.sql").write_text('MODEL (description "Input"); SELECT 1 AS a, 2 AS b')
    sources: Path = tmp_path / "sources"
    sources.mkdir()
    (sources / "orders.yml").write_text(
        "sources:\n  - name: input_source\n    schema: raw\n    table: orders\n    columns:\n      - name: a\n        type: INTEGER\n      - name: b\n        type: INTEGER\n"
    )
    seeds: Path = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "input_seed.csv").write_text("a,b\n1,2\n")
    (seeds / "schema.yml").write_text(
        "seeds:\n  - name: input_seed\n    columns:\n      - name: a\n        type: INTEGER\n      - name: b\n        type: INTEGER\n"
    )
    model: Path = models / "orders.sql"
    model.write_text('MODEL (description "Orders"); ' + test_case.sql)
    assert main(["--project-dir", str(tmp_path), "compile", "--json"]) == bool(
        test_case.expected_findings
    )
    before: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert (
        sum(item["code"] == "SQBRSQL042" for item in before["diagnostics"])
        == test_case.expected_findings
    )
    assert main(["--project-dir", str(tmp_path), "format", "--fix", "--json"]) == 0
    fixed: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert (
        sum(item["status"] == "applied" for item in fixed["rule_fixes"])
        == test_case.expected_applied
    )
    assert main(["--project-dir", str(tmp_path), "compile", "--json"]) == bool(
        test_case.expected_remaining
    )
    after: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert (
        sum(item["code"] == "SQBRSQL042" for item in after["diagnostics"])
        == test_case.expected_remaining
    )


@pytest.mark.parametrize(
    "test_case",
    [
        CteOutputRuleTestCase(
            "group grain is preserved",
            "WITH prepared AS (SELECT a, COUNT(*) AS n FROM (VALUES (1), (2)) AS items(a) GROUP BY a), final AS (SELECT n FROM prepared) SELECT * FROM final",
            1,
            1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unused_group_key_when_fixing_then_group_cardinality_is_preserved(
    test_case: CteOutputRuleTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = ["SQBRSQL042"]\n'
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text("MODEL (); " + test_case.sql)
    assert main(["--project-dir", str(tmp_path), "format", "--fix", "--json"]) == 0
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert (
        sum(item["status"] == "applied" for item in payload["rule_fixes"])
        == test_case.expected_applied
    )
    with duckdb.connect() as connection:
        expected: list[tuple[Any, ...]] = connection.execute(test_case.sql).fetchall()
        actual: list[tuple[Any, ...]] = connection.execute(
            model.read_text().split(";", 1)[1]
        ).fetchall()
    assert actual == expected == [(1,), (1,)]
    assert "GROUP BY a" in " ".join(model.read_text().split())


@pytest.mark.parametrize(
    "test_case",
    [
        CteOutputRuleTestCase(
            "SQL test fixtures are exempt",
            'WITH imported AS (SELECT * FROM __ref("input")), final AS (SELECT a FROM imported) SELECT * FROM final',
            0,
            0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unused_fixture_columns_when_compiling_then_fixture_contract_is_exempt(
    test_case: CteOutputRuleTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = ["SQBRSQL042"]\n'
    )
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "input.sql").write_text(
        "MODEL (); SELECT CAST(1 AS INTEGER) AS a, CAST(2 AS INTEGER) AS b"
    )
    (models / "orders.sql").write_text("MODEL (); " + test_case.sql)
    fixture: Path = tmp_path / "tests" / "unit" / "orders.sql"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(
        "TEST (); WITH __ref__input AS (SELECT 1 AS a, 2 AS b), __expected__orders AS (SELECT 1 AS a) SELECT 1"
    )
    assert main(["--project-dir", str(tmp_path), "compile", "--json"]) == 0
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert (
        sum(item["code"] == "SQBRSQL042" for item in payload["diagnostics"])
        == test_case.expected_findings
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-vv"]))
