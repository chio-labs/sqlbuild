"""Integration coverage for compiler-integrated built-in and custom rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    RulesIntegrationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("selected SQL rule blocks artifacts", 1, "SQBRSQL004")],
    ids=lambda case: case.description,
)
def test_given_selected_sql_rule_when_compiling_then_authored_diagnostic_blocks_artifacts(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL004"]\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id FROM orders LIMIT 1\n',
        encoding="utf-8",
    )

    first_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--manifest"])
    first: dict[str, object] = json.loads(capsys.readouterr().out)
    second_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--manifest"])
    second: dict[str, object] = json.loads(capsys.readouterr().out)
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id FROM orders ORDER BY order_id LIMIT 1\n',
        encoding="utf-8",
    )
    third_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json", "--manifest"])
    third: dict[str, object] = json.loads(capsys.readouterr().out)

    assert first_exit == second_exit == test_case.expected_exit_code
    diagnostics: object = first["diagnostics"]
    assert isinstance(diagnostics, list)
    assert diagnostics[0]["code"] == test_case.expected_code
    assert diagnostics[0]["path"] == "models/orders.sql"
    assert second["compile_timings"]["rule_cache_hits"] == 1
    assert third_exit == 0
    assert third["compile_timings"]["rule_cache_misses"] == 1
    assert third["diagnostics"] == []
    assert (tmp_path / "target" / "manifest.json").is_file()


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("custom rule is enforced and cached", 1, "XSQBRARCH001")],
    ids=lambda case: case.description,
)
def test_given_typed_custom_rule_when_compiling_then_same_rule_is_enforced_and_cached(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n'
        '[rules]\nselect = ["XSQBRARCH001"]\n\n'
        "[rules.thresholds]\nmin_custom_rule_test_cases = 0\n",
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text('MODEL (description "Orders");\nSELECT 1 AS order_id\n', encoding="utf-8")
    rule_file: Path = tmp_path / "rules" / "architecture.py"
    rule_file.parent.mkdir()
    rule_file.write_text(
        """from sqlbuild.rules import Finding, Model, RuleContext, rule

@rule(
    code="XSQBRARCH001",
    message="Final models must use the final directory",
    remediation="Move this model beneath models/final/.",
)
def final_directory(*, model: Model, ctx: RuleContext) -> list[Finding]:
    return [] if "final" in model.path.parts else [ctx.finding(subject=model)]
""",
        encoding="utf-8",
    )

    first_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json"])
    first: dict[str, object] = json.loads(capsys.readouterr().out)
    second_exit: int = main(["--project-dir", str(tmp_path), "compile", "--json"])
    second: dict[str, object] = json.loads(capsys.readouterr().out)

    assert first_exit == second_exit == test_case.expected_exit_code
    assert first["diagnostics"][0]["code"] == test_case.expected_code
    assert second["compile_timings"]["rule_cache_hits"] >= 1
    host_inputs: Path = tmp_path / "target" / "rules-cache" / "host-inputs"
    assert not tuple(host_inputs.glob("*.pickle"))


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("focused SQL rule reports requested code", 1, "SQBRSQL004")],
    ids=lambda case: case.description,
)
def test_given_project_when_running_focused_rule_family_then_only_that_family_runs(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id FROM orders LIMIT 1\n',
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "rules",
            "--json",
            "run",
            "SQBRSQL004",
        ]
    )

    assert exit_code == test_case.expected_exit_code
    captured: CaptureResult[str] = capsys.readouterr()
    payload: dict[str, object] = json.loads(captured.out)
    assert test_case.expected_code in json.dumps(payload["findings"])
    assert "Rule selection SQBRSQL004 failed with 1 finding(s)." in captured.err


@pytest.mark.parametrize(
    "test_case",
    [RulesIntegrationTestCase("SQL rule exception suppresses finding", 0, "SQBRSQL004")],
    ids=lambda case: case.description,
)
def test_given_sql_rule_exception_when_compiling_then_unified_suppression_is_applied(
    test_case: RulesIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n'
        '[rules]\nselect = ["SQBRSQL004"]\n\n'
        '[[rules.rule_exceptions]]\nrule = "SQBRSQL004"\n'
        'path = "models/orders.sql"\nreason = "The fixture intentionally selects one row."\n',
        encoding="utf-8",
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id FROM orders LIMIT 1\n',
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--json"])

    assert exit_code == test_case.expected_exit_code
    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert test_case.expected_code not in json.dumps(payload["diagnostics"])
