"""Unit tests for lint and format orchestration over a synthetic project."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.lint._helpers.suppressions import apply_suppressions
from sqlbuild.lint.constants import LINT_ENGINE_SQLBUILD, VIOLATION_SEVERITY_FAULT
from sqlbuild.lint.main.run_format import run_format
from sqlbuild.lint.main.run_lint import run_lint
from sqlbuild.lint.models import LintConfig, LintRunResult, LintViolation
from tests.unit.src.sqlbuild.lint._test_types import (
    FormatNewlineTestCase,
    FormatProjectTestCase,
    LintBehaviorTestCase,
    LintProjectTestCase,
)

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
            description="schema declarations are discovered for linting",
            files={"schemas/order.sql": "SCHEMA (name order, columns (id (type INTEGER)));\n"},
            expected_fault_codes=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_synthetic_project_when_linting_then_results_match_expected(
    test_case: LintProjectTestCase, tmp_path: Path
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    relative_path: str
    contents: str
    for relative_path, contents in {**test_case.files, **test_case.extra_files}.items():
        target: Path = tmp_path / relative_path
        _ = target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(contents, encoding="utf-8")
    result: LintRunResult = run_lint(
        project_dir=tmp_path,
        config=LintConfig(),
    )
    assert result.files_checked == test_case.expected_files_checked
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
            expected_formatted_count=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_synthetic_project_when_formatting_then_results_match_expected(
    test_case: FormatProjectTestCase, tmp_path: Path
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    relative_path: str
    contents: str
    for relative_path, contents in test_case.files.items():
        target: Path = tmp_path / relative_path
        _ = target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(contents, encoding="utf-8")
    result: LintRunResult = run_format(project_dir=tmp_path, config=LintConfig())
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


@pytest.mark.parametrize(
    "test_case",
    [
        FormatNewlineTestCase(
            description="CRLF newline style is preserved",
            contents=(
                b"-- Description.\r\nMODEL (\r\n  materialized table  \r\n);\r\nSELECT 1\r\n"
            ),
            expected_newline=b"\r\n",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_authored_newline_style_when_formatting_then_style_is_preserved(
    test_case: FormatNewlineTestCase, tmp_path: Path
) -> None:
    target: Path = tmp_path / "models" / "crlf.sql"
    _ = target.parent.mkdir(parents=True)
    target.write_bytes(test_case.contents)
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")

    _ = run_format(project_dir=tmp_path, config=LintConfig())
    second: LintRunResult = run_format(project_dir=tmp_path, config=LintConfig())

    written: bytes = target.read_bytes()
    assert test_case.expected_newline in written
    assert written.count(test_case.expected_newline) == written.count(b"\n")
    assert second.formatted_files == ()


@pytest.mark.parametrize(
    "test_case",
    [LintBehaviorTestCase(description="Unicode source span mapping", expected_value=(2, 44))],
    ids=lambda case: case.description,
)
def test_given_non_ascii_sql_when_native_linting_then_span_maps_to_authored_column(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    target: Path = tmp_path / "models" / "unicode.sql"
    _ = target.parent.mkdir(parents=True)
    _ = target.write_text(
        "MODEL (description \"ok\");\nSELECT 'é' AS label FROM items WHERE value = NULL\n",
        encoding="utf-8",
    )

    result: LintRunResult = run_lint(
        project_dir=tmp_path,
        config=LintConfig(dialect="duckdb"),
    )

    assert tuple(item.code for item in result.violations) == ("SQBL001",)
    assert (result.violations[0].line, result.violations[0].column) == test_case.expected_value
    assert (result.violations[0].end_line, result.violations[0].end_column) == (2, 45)
    assert result.violations[0].remediation == ("Use IS NULL or IS NOT NULL when testing for NULL.")


@pytest.mark.parametrize(
    "test_case",
    [LintBehaviorTestCase(description="canonical idempotent SQL body", expected_value=1)],
    ids=lambda case: case.description,
)
def test_given_comment_free_body_when_formatting_twice_then_output_is_canonical_and_idempotent(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    target: Path = tmp_path / "models" / "messy.sql"
    target.parent.mkdir()
    _ = target.write_text(
        'MODEL (description "ok");\nselect a,b from items where a=1\n',
        encoding="utf-8",
    )

    first: LintRunResult = run_format(
        project_dir=tmp_path,
        config=LintConfig(dialect="duckdb"),
    )
    second: LintRunResult = run_format(
        project_dir=tmp_path,
        config=LintConfig(dialect="duckdb"),
    )

    assert len(first.formatted_files) == test_case.expected_value
    assert second.formatted_files == ()
    assert "SELECT\n  a,\n  b\nFROM items\nWHERE\n  a = 1\n" in target.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "test_case",
    [
        LintBehaviorTestCase(
            description="canonical commented SQL body",
            expected_value="/* preserve exactly */",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_commented_body_when_formatting_then_comment_is_preserved_in_canonical_output(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    contents: str = 'MODEL (description "ok");\nSELECT a, /* preserve exactly */ b FROM items\n'
    target: Path = tmp_path / "models" / "commented_body.sql"
    target.parent.mkdir()
    _ = target.write_text(contents, encoding="utf-8")

    result: LintRunResult = run_format(
        project_dir=tmp_path,
        config=LintConfig(dialect="duckdb"),
    )

    assert result.formatted_files == (target,)
    written: str = target.read_text(encoding="utf-8")
    assert str(test_case.expected_value) in written
    assert written == (
        'MODEL (description "ok");\nSELECT\n  a, /* preserve exactly */\n  b\nFROM items\n'
    )


@pytest.mark.parametrize(
    "test_case",
    [LintBehaviorTestCase(description="reasoned matching local suppression", expected_value=())],
    ids=lambda case: case.description,
)
def test_given_reasoned_local_suppression_when_linting_then_matching_warning_is_removed(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    target: Path = tmp_path / "models" / "sample.sql"
    target.parent.mkdir()
    _ = target.write_text(
        'MODEL (description "ok");\n'
        "-- sqb: ignore SQBL004 because this fixture intentionally samples one row\n"
        "SELECT value FROM items LIMIT 1\n",
        encoding="utf-8",
    )

    result: LintRunResult = run_lint(
        project_dir=tmp_path,
        config=LintConfig(dialect="duckdb"),
    )

    assert result.violations == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        LintBehaviorTestCase(
            description="unused local suppression",
            expected_value="Unused suppression for SQBL004",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unused_local_suppression_when_linting_then_reports_suppression_warning(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
) -> None:
    _ = test_case
    _ = (tmp_path / "sqlbuild_project.toml").write_text(PROJECT_TOML, encoding="utf-8")
    target: Path = tmp_path / "models" / "ordered.sql"
    target.parent.mkdir()
    _ = target.write_text(
        'MODEL (description "ok");\n'
        "-- sqb: ignore SQBL004 because this query used to sample one row\n"
        "SELECT value FROM items ORDER BY value LIMIT 1\n",
        encoding="utf-8",
    )

    result: LintRunResult = run_lint(
        project_dir=tmp_path,
        config=LintConfig(dialect="duckdb"),
    )

    assert tuple(item.code for item in result.violations) == ("SQBL000",)
    assert result.violations[0].message == test_case.expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        LintBehaviorTestCase(
            description="mandatory fault suppression attempt",
            expected_value={"SQBL000", "description-present"},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_header_fault_suppression_when_linting_then_mandatory_fault_remains(
    test_case: LintBehaviorTestCase,
    tmp_path: Path,
) -> None:
    _ = test_case
    target: Path = tmp_path / "models" / "missing_description.sql"
    contents: str = (
        "-- sqb: ignore description-present because this must not bypass compiler policy\n"
        "MODEL (materialized table);\n"
    )
    mandatory: LintViolation = LintViolation(
        file_path=target,
        line=2,
        column=1,
        code="description-present",
        message="MODEL header must include a description",
        severity=VIOLATION_SEVERITY_FAULT,
        engine=LINT_ENGINE_SQLBUILD,
    )

    result: list[LintViolation] = apply_suppressions(
        violations=[mandatory], contents_by_path={target: contents}
    )

    assert {item.code for item in result} == test_case.expected_value
