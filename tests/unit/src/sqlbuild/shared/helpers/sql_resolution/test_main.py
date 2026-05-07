from __future__ import annotations

import pytest

from sqlbuild.shared.helpers.sql_resolution import assert_no_unresolved_sql_markers
from tests.unit.src.sqlbuild.shared.helpers.sql_resolution._test_types import (
    AssertNoUnresolvedSqlMarkersTestCase,
)

UNRESOLVED_SQL_MARKER_TEST_CASES: list[AssertNoUnresolvedSqlMarkersTestCase] = [
    AssertNoUnresolvedSqlMarkersTestCase(
        description="raises on unresolved ref marker",
        sql='SELECT * FROM __ref("orders")',
        context="audit 'not_null' planned SQL",
        expected_error_fragment=r"still contains unresolved __ref\(\) markers",
        expected_code="R001",
    ),
    AssertNoUnresolvedSqlMarkersTestCase(
        description="raises on unresolved source marker",
        sql='SELECT * FROM __source("raw_orders")',
        context="audit 'not_null' executable SQL",
        expected_error_fragment=r"still contains unresolved __source\(\) markers",
        expected_code="R003",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    UNRESOLVED_SQL_MARKER_TEST_CASES,
    ids=[case.description for case in UNRESOLVED_SQL_MARKER_TEST_CASES],
)
def test_given_unresolved_executable_sql_when_validating_then_it_raises_clear_error(
    test_case: AssertNoUnresolvedSqlMarkersTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment) as error_info:
        assert_no_unresolved_sql_markers(sql=test_case.sql, context=test_case.context)

    assert getattr(error_info.value, "code", None) == test_case.expected_code


@pytest.mark.parametrize(
    "test_case",
    [
        AssertNoUnresolvedSqlMarkersTestCase(
            description="passes for resolved executable sql",
            sql="SELECT * FROM main.orders",
            context="audit 'not_null' executable SQL",
            expected_error_fragment="",
        )
    ],
    ids=["passes for resolved executable sql"],
)
def test_given_resolved_executable_sql_when_validating_then_it_passes(
    test_case: AssertNoUnresolvedSqlMarkersTestCase,
) -> None:
    assert_no_unresolved_sql_markers(sql=test_case.sql, context=test_case.context)
    assert test_case.expected_error_fragment == ""
