"""Real-CLI coverage for forbidding Rule exceptions, scoped ignores and inline suppressions."""

from __future__ import annotations

from pathlib import Path

import pytest
from _pytest.capture import CaptureResult

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.cli.commands.main._test_types import (
    FormatExceptionPolicyTestCase,
    RuleExceptionPolicyTestCase,
)

_EXCEPTION: str = (
    '[[rules.rule_exceptions]]\nrule = "SQBRSQL004"\npath = "models/customers.sql"\n'
    'reason = "The sample intentionally keeps one row."\n'
)
_IGNORE: str = (
    '[[rules.rule_ignores]]\nrules = ["SQBRSQL004"]\npaths = ["models/**"]\n'
    'reason = "Samples intentionally keep one row."\n'
)
_DIRECTIVE: str = "-- sqb: ignore SQBRSQL004 because the sample intentionally keeps one row\n"
_SETTING_HELP: str = "[rules]\n            allow_exceptions = true"


@pytest.mark.parametrize(
    "test_case",
    [
        RuleExceptionPolicyTestCase(
            description="exception forbidden",
            rules_toml=f"allow_exceptions = false\n\n{_EXCEPTION}",
            directive="",
            expected_exit_code=1,
            expected_fragments=(
                "sqlbuild_project.toml has 1 [[rules.rule_exceptions]] entry",
                "sets [rules] allow_exceptions = false",
                _SETTING_HELP,
            ),
        ),
        RuleExceptionPolicyTestCase(
            description="scoped ignore forbidden",
            rules_toml=f"allow_exceptions = false\n\n{_IGNORE}",
            directive="",
            expected_exit_code=1,
            expected_fragments=("1 [[rules.rule_ignores]] entry", _SETTING_HELP),
        ),
        RuleExceptionPolicyTestCase(
            description="inline suppression forbidden",
            rules_toml="allow_exceptions = false\n",
            directive=_DIRECTIVE,
            expected_exit_code=1,
            expected_fragments=(
                "SQBRSQL000",
                "Inline Rule suppressions are not allowed in this project",
                "SQBRSQL004",
                "allow_exceptions = true",
            ),
        ),
        RuleExceptionPolicyTestCase(
            description="project-wide ignore stays allowed",
            rules_toml='allow_exceptions = false\nignore = ["SQBRSQL004"]\n',
            directive="",
            expected_exit_code=0,
        ),
        RuleExceptionPolicyTestCase(
            description="exception allowed explicitly",
            rules_toml=f"allow_exceptions = true\n\n{_EXCEPTION}",
            directive="",
            expected_exit_code=0,
        ),
        RuleExceptionPolicyTestCase(
            description="exception allowed by default",
            rules_toml=_EXCEPTION,
            directive="",
            expected_exit_code=0,
        ),
        RuleExceptionPolicyTestCase(
            description="inline suppression allowed by default",
            rules_toml="",
            directive=_DIRECTIVE,
            expected_exit_code=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_allow_exceptions_setting_when_compiling_then_escape_hatches_follow_it(
    test_case: RuleExceptionPolicyTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL004"]\n'
        f"{test_case.rules_toml}",
        encoding="utf-8",
    )
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "customers.sql").write_text(
        "MODEL (description 'Customer sample.');\n"
        "WITH customers AS (SELECT 1 AS customer_id)\n"
        f"{test_case.directive}SELECT customer_id FROM customers LIMIT 1\n",
        encoding="utf-8",
    )

    exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])
    output: CaptureResult[str] = capsys.readouterr()

    assert exit_code == test_case.expected_exit_code, output.out + output.err
    for fragment in test_case.expected_fragments:
        assert fragment in output.out + output.err


@pytest.mark.parametrize(
    "test_case",
    [
        FormatExceptionPolicyTestCase(
            description="string false is rejected like compile",
            setting='allow_exceptions = "false"',
            expected_exit_code=1,
            expected_fragment="invalid rules config",
            expected_compile_fragment="invalid rules config",
        ),
        FormatExceptionPolicyTestCase(
            description="boolean false rejects the inline suppression",
            setting="allow_exceptions = false",
            expected_exit_code=1,
            expected_fragment="Inline Rule suppressions are not allowed in this project",
            expected_compile_fragment="Inline Rule suppressions are not allowed in this project",
        ),
        FormatExceptionPolicyTestCase(
            description="boolean true keeps the inline suppression",
            setting="allow_exceptions = true",
            expected_exit_code=0,
            expected_fragment="FAULT=0",
            expected_compile_fragment="",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_allow_exceptions_setting_when_formatting_then_it_is_validated_like_compile(
    test_case: FormatExceptionPolicyTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n\n[rules]\nselect = ["SQBRSQL004"]\n'
        f"{test_case.setting}\n",
        encoding="utf-8",
    )
    models: Path = tmp_path / "models"
    models.mkdir()
    (models / "customers.sql").write_text(
        "MODEL (description 'Customer sample.');\n"
        "WITH customers AS (\n  SELECT 1 AS customer_id\n)\n\n"
        f"SELECT customer_id\nFROM customers\n{_DIRECTIVE}LIMIT 1\n",
        encoding="utf-8",
    )

    format_exit_code: int = main(["--project-dir", str(tmp_path), "format", "--check"])
    format_output: CaptureResult[str] = capsys.readouterr()
    compile_exit_code: int = main(["--project-dir", str(tmp_path), "compile", "--no-cache"])
    compile_output: CaptureResult[str] = capsys.readouterr()

    assert format_exit_code == test_case.expected_exit_code, format_output.out + format_output.err
    assert compile_exit_code == test_case.expected_exit_code
    assert test_case.expected_fragment in format_output.out + format_output.err
    assert test_case.expected_compile_fragment in compile_output.out + compile_output.err


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
