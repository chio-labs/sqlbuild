"""Unit tests for the sqb lint and sqb format commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.unit.src.sqlbuild.lint._test_types import FormatCliTestCase, LintCliTestCase

CLEAN_MODEL: str = 'MODEL (\n  materialized table,\n  description "ok"\n);\nSELECT 1 AS x FROM t\n'
COMMENTED_MODEL: str = "-- A comment.\nMODEL (\n  materialized table\n);\nSELECT 1 AS x FROM t\n"
NO_DESCRIPTION_MODEL: str = "MODEL (\n  materialized table\n);\nSELECT 1 AS x FROM t\n"


@pytest.mark.parametrize(
    "test_case",
    [
        LintCliTestCase(
            description="lint reports violations and exits nonzero",
            files={"models/no_description.sql": NO_DESCRIPTION_MODEL},
            expected_exit_code=1,
            expected_output_fragments=("description-present", "FAULT=1"),
        ),
        LintCliTestCase(
            description="lint on a clean project exits zero",
            files={"models/fine.sql": CLEAN_MODEL},
            expected_exit_code=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_running_lint_then_exit_code_and_output_match_expected(
    test_case: LintCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file_relative_path: str
    file_contents: str
    for file_relative_path, file_contents in test_case.files.items():
        write_target: Path = tmp_path / file_relative_path
        _ = write_target.parent.mkdir(parents=True, exist_ok=True)
        _ = write_target.write_text(file_contents, encoding="utf-8")
    exit_code: int = main(["--project-dir", str(tmp_path), "lint", "--no-sqruff"])
    assert exit_code == test_case.expected_exit_code
    output: str = capsys.readouterr().out
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output


@pytest.mark.parametrize(
    "test_case",
    [
        FormatCliTestCase(
            description="format relocates leading comments in place",
            files={"models/commented.sql": COMMENTED_MODEL},
            expected_exit_code=0,
            expected_output_fragments=("Formatted files:",),
            expected_file_fragments={"models/commented.sql": 'description "A comment.",'},
        ),
        FormatCliTestCase(
            description="format exits nonzero when faults remain",
            files={"models/no_description.sql": NO_DESCRIPTION_MODEL},
            expected_exit_code=1,
            expected_output_fragments=("FAULT=1",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_running_format_then_results_match_expected(
    test_case: FormatCliTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    file_relative_path: str
    file_contents: str
    for file_relative_path, file_contents in test_case.files.items():
        write_target: Path = tmp_path / file_relative_path
        _ = write_target.parent.mkdir(parents=True, exist_ok=True)
        _ = write_target.write_text(file_contents, encoding="utf-8")
    exit_code: int = main(["--project-dir", str(tmp_path), "format", "--no-sqruff"])
    assert exit_code == test_case.expected_exit_code
    output: str = capsys.readouterr().out
    fragment: str
    for fragment in test_case.expected_output_fragments:
        assert fragment in output
    relative_path: str
    file_fragment: str
    for relative_path, file_fragment in test_case.expected_file_fragments.items():
        written: str = (tmp_path / relative_path).read_text(encoding="utf-8")
        assert file_fragment in written
