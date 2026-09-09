"""Behavior tests for the source-rewriting format command."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.unit.src.sqlbuild.lint._test_types import FormatCliTestCase

PROJECT_TOML: str = 'name = "demo"\nadapter = "duckdb"\n'


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCliTestCase("writes formatted SQL", (), 0, "Formatted files:", True),
        FormatCliTestCase("check reports changes", ("--check",), 1, "Would format files:"),
        FormatCliTestCase("diff prints without writing", ("--diff",), 0, "+SELECT"),
    ],
    ids=lambda case: case.description,
)
def test_given_unformatted_sql_when_formatting_then_mode_controls_writes(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    original: str = 'MODEL (description "Orders");\nselect order_id,status from orders\n'
    model.write_text(original, encoding="utf-8")

    exit_code: int = main(["--project-dir", str(tmp_path), "format", *test_case.arguments])

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment in capsys.readouterr().out
    formatted: str = model.read_text(encoding="utf-8")
    assert (formatted != original) is test_case.expected_writes


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("legacy lint config is rejected", (), 1, "unsupported legacy")],
    ids=lambda case: case.description,
)
def test_given_legacy_lint_configuration_when_formatting_then_it_is_rejected(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        f'{PROJECT_TOML}\n[lint]\nselect = ["SQBRSQL"]\n', encoding="utf-8"
    )
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text('MODEL (description "Orders");\nSELECT 1 AS order_id\n', encoding="utf-8")

    exit_code: int = main(["--project-dir", str(tmp_path), "compile"])

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment in capsys.readouterr().err


@pytest.mark.parametrize(
    "test_case",
    [FormatCliTestCase("format does not enforce unselected Rules", (), 0, "SQBRSQL004")],
    ids=lambda case: case.description,
)
def test_given_unselected_sql_rule_finding_when_formatting_then_rule_is_not_enforced(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    model: Path = tmp_path / "models" / "orders.sql"
    model.parent.mkdir()
    model.write_text(
        'MODEL (description "Orders");\nSELECT order_id FROM orders LIMIT 1\n',
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "format"])

    assert exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment not in capsys.readouterr().out
