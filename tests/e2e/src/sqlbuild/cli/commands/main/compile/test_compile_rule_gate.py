"""E2E tests for SQL test planning errors reported when compile rules fail."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    RuleGatedTestDiagnosticsTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    build_rule_gated_test_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_MISSING_MOCK_MESSAGE: str = (
    "test 'orders_case': model 'orders' references __source('raw_refunds') which has no mock"
)
_EXPECTED_DIAGNOSTICS: tuple[tuple[str, str, str], ...] = (
    ("rule", "SQBRMODEL102", "SELECT * is allowed only inside dependency import CTEs"),
    ("test", "S000", _MISSING_MOCK_MESSAGE),
)
_EXPECTED_TEXT_LINES: tuple[str, ...] = (
    "error[SQBRMODEL102]: SELECT * is allowed only inside dependency import CTEs",
    f"error[S000]: {_MISSING_MOCK_MESSAGE}",
)


@pytest.mark.parametrize(
    "test_case",
    (
        RuleGatedTestDiagnosticsTestCase(
            description="inline artifact writer",
            filler_model_count=0,
            extra_args=(),
            expected_diagnostics=_EXPECTED_DIAGNOSTICS,
            expected_text_lines=_EXPECTED_TEXT_LINES,
        ),
        RuleGatedTestDiagnosticsTestCase(
            description="background artifact preparation",
            filler_model_count=130,
            extra_args=("--no-cache",),
            expected_diagnostics=_EXPECTED_DIAGNOSTICS,
            expected_text_lines=_EXPECTED_TEXT_LINES,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_rule_error_and_test_missing_mock_when_compiling_then_both_errors_are_reported(
    test_case: RuleGatedTestDiagnosticsTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="rule_gated_project",
        repo_files=build_rule_gated_test_project_files(
            filler_model_count=test_case.filler_model_count
        ),
    )

    text_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile", *test_case.extra_args), project_dir=project_dir
    )
    json_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile", "--json", *test_case.extra_args),
        project_dir=project_dir,
    )

    text_output: str = text_result.stdout + text_result.stderr
    assert text_result.returncode == 1, text_output
    for line in test_case.expected_text_lines:
        assert text_result.stdout.count(line) == 1, text_output
    assert "2 errors, 0 warnings" in text_result.stdout, text_output
    assert json_result.returncode == 1, json_result.stdout + json_result.stderr
    payload: dict[str, Any] = json.loads(json_result.stdout)
    assert payload["has_errors"] is True
    assert payload["summary"]["errors"] == len(test_case.expected_diagnostics)
    assert [
        (diagnostic["phase"], diagnostic["code"], diagnostic["message"])
        for diagnostic in payload["diagnostics"]
    ] == list(test_case.expected_diagnostics)
    assert not (project_dir / "target" / "compiled" / "tests").exists()
