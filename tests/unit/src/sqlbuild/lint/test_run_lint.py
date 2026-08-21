"""Unit tests for lint and format orchestration over a synthetic project."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.lint.main.run_format import run_format
from sqlbuild.lint.main.run_lint import run_lint
from sqlbuild.lint.models import LintConfig, LintRunResult
from tests.unit.src.sqlbuild.lint._test_types import FormatProjectTestCase, LintProjectTestCase

CLEAN_MODEL: str = 'MODEL (\n  materialized table,\n  description "ok"\n);\nSELECT 1 AS x FROM t\n'
NO_DESCRIPTION_MODEL: str = "MODEL (\n  materialized table\n);\nSELECT 1 AS x FROM t\n"
PROJECT_TOML: str = 'name = "demo"\nadapter = "duckdb"\n'


@pytest.mark.parametrize(
    "test_case",
    [
        LintProjectTestCase(
            description="model without description faults",
            files={"models/no_description.sql": NO_DESCRIPTION_MODEL},
            expected_fault_codes=(("no_description.sql", "description-present"),),
        ),
        LintProjectTestCase(
            description="clean project reports no violations",
            files={"models/fine.sql": CLEAN_MODEL},
            expected_fault_codes=(),
        ),
        LintProjectTestCase(
            description="sqruff engine violations are reported when enabled",
            extra_files={"sqlbuild_project.toml": PROJECT_TOML},
            files={
                "models/messy.sql": (
                    'MODEL (\n  materialized table,\n  description "ok"\n);\n'
                    "SELECT 1 AS x\n  FROM t\n"
                )
            },
            sqruff_enabled=True,
            expected_fault_codes=(),
            expected_sqruff_engine_fault=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_synthetic_project_when_linting_then_results_match_expected(
    test_case: LintProjectTestCase, tmp_path: Path
) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in {**test_case.files, **test_case.extra_files}.items():
        target: Path = tmp_path / relative_path
        _ = target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(contents, encoding="utf-8")
    result: LintRunResult = run_lint(
        project_dir=tmp_path,
        config=LintConfig(sqruff_enabled=test_case.sqruff_enabled),
    )
    assert result.files_checked == len(test_case.files)
    codes: set = {(violation.file_path.name, violation.code) for violation in result.violations}
    expected_code: tuple[str, str]
    for expected_code in test_case.expected_fault_codes:
        assert expected_code in codes


@pytest.mark.parametrize(
    "test_case",
    [
        FormatProjectTestCase(
            description="leading comment is relocated into the description",
            files={
                "models/commented.sql": (
                    "-- A comment.\nMODEL (\n  materialized table\n);\nSELECT 1 AS x FROM t\n"
                )
            },
            expected_written_fragments={"models/commented.sql": 'description "A comment.",'},
            expected_fault_codes=(),
            expected_formatted_count=1,
        ),
        FormatProjectTestCase(
            description="unfixable faults remain after formatting",
            files={"models/no_description.sql": NO_DESCRIPTION_MODEL},
            expected_written_fragments={},
            expected_fault_codes=("description-present",),
            expected_formatted_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_synthetic_project_when_formatting_then_results_match_expected(
    test_case: FormatProjectTestCase, tmp_path: Path
) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in test_case.files.items():
        target: Path = tmp_path / relative_path
        _ = target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(contents, encoding="utf-8")
    result: LintRunResult = run_format(
        project_dir=tmp_path, config=LintConfig(sqruff_enabled=False)
    )
    assert len(result.formatted_files) == test_case.expected_formatted_count
    remaining: tuple = tuple(violation.code for violation in result.faults)
    fault_code: str
    for fault_code in test_case.expected_fault_codes:
        assert fault_code in remaining
    relative_path: str
    fragment: str
    for relative_path, fragment in test_case.expected_written_fragments.items():
        written: str = (tmp_path / relative_path).read_text(encoding="utf-8")
        assert fragment in written


def test_given_crlf_file_when_formatting_then_newline_style_is_preserved(tmp_path: Path) -> None:
    target: Path = tmp_path / "models" / "crlf.sql"
    _ = target.parent.mkdir(parents=True)
    target.write_bytes(
        b"-- Description.\r\nMODEL (\r\n  materialized table  \r\n);\r\nSELECT 1\r\n"
    )

    _ = run_format(project_dir=tmp_path, config=LintConfig(sqruff_enabled=False))

    written: bytes = target.read_bytes()
    assert b"\r\n" in written
    assert written.count(b"\r\n") == written.count(b"\n")
