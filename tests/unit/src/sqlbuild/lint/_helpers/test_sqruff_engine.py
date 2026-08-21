"""Unit tests for the sqruff engine wrapper."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sqlbuild.lint._helpers import sqruff_engine
from sqlbuild.lint._helpers.headers import scan_headers, sql_body_ranges
from sqlbuild.lint._helpers.sqruff_engine import run_sqruff_fix, run_sqruff_lint
from sqlbuild.lint.models import LintConfig
from tests.unit.src.sqlbuild.lint._helpers._test_types import (
    SqruffEngineFixTestCase,
    SqruffEngineLintTestCase,
    SqruffNoBodiesTestCase,
)

FILE_PATH: Path = Path("models/example.sql")
CONFIG: LintConfig = LintConfig(sqruff_enabled=True)


@pytest.mark.parametrize(
    "test_case",
    [
        SqruffEngineLintTestCase(
            description="sqruff warning maps back onto the original file position",
            contents="MODEL (\n  materialized table\n);\nSELECT 1\n",
            stdout=(
                '{"body_0.sql": [{"range": {"start": {"line": 0, "character": 7}, '
                '"end": {"line": 0, "character": 8}}, "message": "Keyword case.", '
                '"severity": "Warning", "source": "sqruff", "code": "LT09"}]}'
            ),
            expected_lines=(4,),
            expected_columns=(8,),
            expected_codes=("LT09",),
        ),
        SqruffEngineLintTestCase(
            description="unknown temp file diagnostics are ignored",
            contents="MODEL (\n  materialized table\n);\nSELECT 1\n",
            stdout='{"other.sql": []}',
            expected_lines=(),
            expected_columns=(),
            expected_codes=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_canned_sqruff_output_when_linting_then_violations_map_to_original_file(
    test_case: SqruffEngineLintTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []

    def fake_run_cli(arguments: list[str]) -> int:
        calls.append(1)
        _ = os.write(1, test_case.stdout.encode("utf-8"))
        return 1

    monkeypatch.setattr(sqruff_engine, "run_cli", fake_run_cli)
    headers: tuple = scan_headers(contents=test_case.contents)
    bodies: dict = {
        Path(FILE_PATH): (
            test_case.contents,
            sql_body_ranges(contents=test_case.contents, headers=headers),
        )
    }
    violations: dict = run_sqruff_lint(bodies=bodies, config=CONFIG, project_dir=Path("."))
    assert calls == [1]
    file_violations: tuple = violations[Path(FILE_PATH)]
    assert tuple(violation.line for violation in file_violations) == test_case.expected_lines
    assert tuple(violation.column for violation in file_violations) == test_case.expected_columns
    assert tuple(violation.code for violation in file_violations) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    [
        SqruffEngineFixTestCase(
            description="fixed body is spliced back without touching the header",
            contents="MODEL (\n  materialized table\n);\nSELECT 1 as a\n",
            fixed_body="SELECT 1 AS a\n",
            expected_contents="MODEL (\n  materialized table\n);\nSELECT 1 AS a\n",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fixed_body_when_formatting_then_original_contents_are_spliced(
    test_case: SqruffEngineFixTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_fix(arguments: list[str]) -> int:
        _ = Path(arguments[-1]).write_text(test_case.fixed_body, encoding="utf-8")
        return 0

    monkeypatch.setattr(sqruff_engine, "run_cli", fake_fix)
    headers: tuple = scan_headers(contents=test_case.contents)
    bodies: dict = {
        Path(FILE_PATH): (
            test_case.contents,
            sql_body_ranges(contents=test_case.contents, headers=headers),
        )
    }
    fixed: dict = run_sqruff_fix(bodies=bodies, config=CONFIG, project_dir=Path("."))
    assert fixed[Path(FILE_PATH)] == test_case.expected_contents


@pytest.mark.parametrize(
    "test_case",
    [
        SqruffNoBodiesTestCase(
            description="no bodies skips the engine entirely",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_no_bodies_when_linting_then_run_cli_is_not_invoked(
    test_case: SqruffNoBodiesTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = test_case
    calls: list[int] = []

    def failing_run_cli(arguments: list[str]) -> int:
        calls.append(1)
        return 0

    monkeypatch.setattr(sqruff_engine, "run_cli", failing_run_cli)
    violations: dict = run_sqruff_lint(bodies={}, config=CONFIG, project_dir=Path("."))
    assert list(violations) == list(test_case.expected_violation_files)
    assert calls == []
