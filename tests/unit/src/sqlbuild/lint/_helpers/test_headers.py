"""Unit tests for the DSL header scanner."""

from __future__ import annotations

import pytest

from sqlbuild.lint._helpers.headers import scan_headers, sql_body_ranges
from tests.unit.src.sqlbuild.lint._helpers._test_types import (
    HeaderSpanTextTestCase,
    ScanHeadersTestCase,
    SqlBodyRangesTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ScanHeadersTestCase(
            description="finds model header",
            contents="MODEL (\n  materialized table\n);\nSELECT 1\n",
            expected_kinds=("MODEL",),
        ),
        ScanHeadersTestCase(
            description="finds scenario test and audit headers in one file",
            contents=(
                'SCENARIO (description "d");\nSELECT 1\n'
                "TEST ();\nSELECT 2\n"
                'AUDIT (name "a");\nSELECT 3\n'
            ),
            expected_kinds=("SCENARIO", "TEST", "AUDIT"),
        ),
        ScanHeadersTestCase(
            description="finds enum and constant declarations",
            contents=(
                "ENUM (name \"status\", members ['a', 'b']);\nCONSTANT (name \"x\", value 1);\n"
            ),
            expected_kinds=("ENUM", "CONSTANT"),
        ),
        ScanHeadersTestCase(
            description="ignores lowercase keyword",
            contents="model (\n  materialized table\n);\nSELECT 1\n",
            expected_kinds=(),
        ),
        ScanHeadersTestCase(
            description="ignores keyword not at line start",
            contents="SELECT 1 FROM MODEL (\n  x\n)\n",
            expected_kinds=(),
        ),
        ScanHeadersTestCase(
            description="handles nested parens and quoted strings",
            contents=(
                "MODEL (\n  columns (\n    a (audits [not_null]),\n  ),\n"
                '  description "has ) paren and \\" quote"\n);\nSELECT 1\n'
            ),
            expected_kinds=("MODEL",),
        ),
        ScanHeadersTestCase(
            description="ignores header-like text inside comments",
            contents=(
                '-- TEST ();\n/*\nMODEL (not a header);\n*/\nMODEL (description "ok");\nSELECT 1\n'
            ),
            expected_kinds=("MODEL",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_contents_when_scanning_headers_then_kinds_match_expected(
    test_case: ScanHeadersTestCase,
) -> None:
    spans: tuple = scan_headers(contents=test_case.contents)
    assert tuple(span.kind for span in spans) == test_case.expected_kinds


@pytest.mark.parametrize(
    "test_case",
    [
        HeaderSpanTextTestCase(
            description="span covers header keyword through terminator",
            contents="MODEL (\n  materialized table\n);\nSELECT 1\n",
            expected_span_text="MODEL (\n  materialized table\n);",
        ),
        HeaderSpanTextTestCase(
            description="span without terminator ends at close paren",
            contents="MODEL (\n  materialized table\n)\nSELECT 1\n",
            expected_span_text="MODEL (\n  materialized table\n)",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_model_file_when_scanning_then_span_covers_header_and_terminator(
    test_case: HeaderSpanTextTestCase,
) -> None:
    spans: tuple = scan_headers(contents=test_case.contents)
    assert len(spans) == 1
    span_text: str = test_case.contents[spans[0].start : spans[0].end]
    assert span_text == test_case.expected_span_text


@pytest.mark.parametrize(
    "test_case",
    [
        SqlBodyRangesTestCase(
            description="bodies exclude headers and keep sql text",
            contents="MODEL (\n  materialized table\n);\nSELECT 1\nTEST ();\nSELECT 2\n",
            expected_fragments=("SELECT 1", "SELECT 2"),
            excluded_fragments=("MODEL", "TEST ()"),
        ),
        SqlBodyRangesTestCase(
            description="trailing body after last header is included",
            contents="TEST ();\nSELECT 42\n",
            expected_fragments=("SELECT 42",),
            excluded_fragments=("TEST ()",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_headers_when_extracting_body_ranges_then_bodies_exclude_headers(
    test_case: SqlBodyRangesTestCase,
) -> None:
    spans: tuple = scan_headers(contents=test_case.contents)
    ranges: tuple = sql_body_ranges(contents=test_case.contents, headers=spans)
    extracted: str = "".join(test_case.contents[start:end] for start, end in ranges)
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in extracted
    for fragment in test_case.excluded_fragments:
        assert fragment not in extracted
