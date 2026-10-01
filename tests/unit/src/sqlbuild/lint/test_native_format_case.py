"""Native formatting and fingerprints keep the case of keyword-named identifiers."""

from __future__ import annotations

import json

import pytest

import sqlbuild._native as native_module
from tests.unit.src.sqlbuild.lint._test_types import KeywordNamedIdentifierFormatTestCase
from tests.unit.src.sqlbuild.lint.helpers import keyword_name_positions


@pytest.mark.parametrize(
    "test_case",
    [
        KeywordNamedIdentifierFormatTestCase(
            description=f"{dialect} {name} as {position}",
            dialect=dialect,
            sql=template.format(name=name),
            name=name,
            expected_name_occurrences=occurrences,
        )
        for dialect, name, position, template, occurrences in keyword_name_positions()
    ],
    ids=lambda case: case.description,
)
def test_given_keyword_named_identifier_when_formatting_then_case_is_kept_and_fingerprinted(
    test_case: KeywordNamedIdentifierFormatTestCase,
) -> None:
    response: dict[str, object] = json.loads(
        native_module.format_sql_json(
            json.dumps({"version": 1, "sql": test_case.sql, "dialect": test_case.dialect})
        )
    )
    printed: str = str(response.get("sql") or "")
    swapped: str = test_case.sql.replace(test_case.name, test_case.name.swapcase())

    assert response["formatted"] is False or (
        printed.count(test_case.name) == test_case.expected_name_occurrences
    ), test_case.description
    assert native_module.query_fingerprint(
        test_case.sql, test_case.dialect
    ) != native_module.query_fingerprint(swapped, test_case.dialect), test_case.description
