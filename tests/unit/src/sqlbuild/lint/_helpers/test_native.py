"""Unit tests for native header lint rules and formatting."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery._helpers.sql.model_files import parse_model_sql
from sqlbuild.lint._helpers.headers import scan_headers
from sqlbuild.lint._helpers.native import format_native_headers, lint_native_headers
from sqlbuild.lint.models import LintConfig
from tests.unit.src.sqlbuild.lint._helpers._test_types import (
    FormatNativeTestCase,
    LintNativeTestCase,
)

FILE_PATH: Path = Path("models/example.sql")
DEFAULT_CONFIG: LintConfig = LintConfig()


@pytest.mark.parametrize(
    "test_case",
    [
        LintNativeTestCase(
            description="model without description faults",
            contents="MODEL (\n  materialized table\n);\nSELECT 1\n",
            expected_codes=("description-present",),
        ),
        LintNativeTestCase(
            description="model with description passes",
            contents='MODEL (\n  materialized table,\n  description "ok"\n);\nSELECT 1\n',
            expected_codes=(),
        ),
        LintNativeTestCase(
            description="scenario without description does not fault",
            contents='SCENARIO (tags: ["x"]);\nSELECT 1\n',
            expected_codes=(),
        ),
        LintNativeTestCase(
            description="long single-line scenario description passes",
            contents=(
                'SCENARIO (description: "'
                + " ".join(f"word{index}" for index in range(400))
                + '");\nSELECT 1\n'
            ),
            expected_codes=(),
        ),
        LintNativeTestCase(
            description="oversized multiline scenario description faults",
            contents=(
                'SCENARIO (description: "'
                + "\\n ".join(f"line {index}" for index in range(11))
                + '");\nSELECT 1\n'
            ),
            expected_codes=("description-length",),
        ),
        LintNativeTestCase(
            description="broken model header faults with parse error",
            contents="MODEL (\n  materialized table,\n  description\n);\nSELECT 1\n",
            expected_codes=("header-parse",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_contents_when_linting_then_codes_match_expected(
    test_case: LintNativeTestCase,
) -> None:
    spans: tuple = scan_headers(contents=test_case.contents)
    violations: tuple = lint_native_headers(
        contents=test_case.contents,
        file_path=FILE_PATH,
        headers=spans,
        config=DEFAULT_CONFIG,
    )
    assert tuple(violation.code for violation in violations) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    [
        FormatNativeTestCase(
            description="leading block comment relocates into description",
            contents="/* Orders daily fact. */\nMODEL (\n  materialized table\n);\nSELECT 1\n",
            expected_contents=(
                'MODEL (\n  description "Orders daily fact.",\n  materialized table\n);\nSELECT 1\n'
            ),
            expected_fault_codes=(),
        ),
        FormatNativeTestCase(
            description="leading line comments relocate into description",
            contents="-- One.\n-- Two.\nMODEL (\n  materialized table\n);\nSELECT 1\n",
            expected_contents=(
                'MODEL (\n  description "One.\nTwo.",\n  materialized table\n);\nSELECT 1\n'
            ),
            expected_fault_codes=(),
        ),
        FormatNativeTestCase(
            description="existing description leaves comment untouched",
            contents=(
                '/* A note. */\nMODEL (\n  materialized table,\n  description "kept"\n);\n'
                "SELECT 1\n"
            ),
            expected_contents=(
                '/* A note. */\nMODEL (\n  materialized table,\n  description "kept"\n);\n'
                "SELECT 1\n"
            ),
            expected_fault_codes=(),
        ),
        FormatNativeTestCase(
            description="trailing whitespace in header is trimmed",
            contents='MODEL ( \n  materialized table,\t\n  description "d" \n);\nSELECT 1\n',
            expected_contents='MODEL (\n  materialized table,\n  description "d"\n);\nSELECT 1\n',
            expected_fault_codes=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_contents_when_formatting_then_contents_match_expected(
    test_case: FormatNativeTestCase,
) -> None:
    updated: str
    faults: tuple
    updated, faults = format_native_headers(
        contents=test_case.contents,
        file_path=FILE_PATH,
        config=DEFAULT_CONFIG,
    )
    assert updated == test_case.expected_contents
    assert tuple(fault.code for fault in faults) == test_case.expected_fault_codes


@pytest.mark.parametrize(
    "test_case",
    [
        FormatNativeTestCase(
            description="oversized relocated comment faults for a human to trim",
            contents=(
                "-- "
                + "\n-- ".join(f"line {index}" for index in range(11))
                + "\nMODEL (\n  materialized table\n);\nSELECT 1\n"
            ),
            expected_contents=(
                'MODEL (\n  description "'
                + "\n".join(f"line {index}" for index in range(11))
                + '",\n  materialized table\n);\nSELECT 1\n'
            ),
            expected_fault_codes=("leading-comment-description",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_oversized_leading_comment_when_formatting_then_relocates_and_faults(
    test_case: FormatNativeTestCase,
) -> None:
    updated: str
    faults: tuple
    updated, faults = format_native_headers(
        contents=test_case.contents,
        file_path=FILE_PATH,
        config=DEFAULT_CONFIG,
    )
    assert updated == test_case.expected_contents
    assert tuple(fault.code for fault in faults) == test_case.expected_fault_codes


@pytest.mark.parametrize(
    "test_case",
    [
        FormatNativeTestCase(
            description="relocated description round trips through the model parser",
            contents="-- The orders fact.\nMODEL (\n  materialized table\n);\nSELECT 1\n",
            expected_contents=(
                'MODEL (\n  description "The orders fact.",\n  materialized table\n);\nSELECT 1\n'
            ),
            expected_fault_codes=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relocated_model_when_parsing_then_description_round_trips(
    test_case: FormatNativeTestCase,
) -> None:
    updated: str
    faults: tuple
    updated, faults = format_native_headers(
        contents=test_case.contents,
        file_path=FILE_PATH,
        config=DEFAULT_CONFIG,
    )
    assert updated == test_case.expected_contents
    assert tuple(fault.code for fault in faults) == ()
    values, _query = parse_model_sql(contents=updated, file_path=FILE_PATH)
    assert values.get("description") == "The orders fact."
