"""Tests for relation naming helpers."""

from __future__ import annotations

import pytest

from sqlbuild.executor.run.helpers.naming import build_qualified_name
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import (
    BuildQualifiedNameTestCase,
)

QUALIFIED_NAME_TEST_CASES: list[BuildQualifiedNameTestCase] = [
    BuildQualifiedNameTestCase(
        description="database and schema and name produces three-part name",
        database="analytics",
        schema="staging",
        name="orders",
        expected_qualified="analytics.staging.orders",
    ),
    BuildQualifiedNameTestCase(
        description="schema and name without database produces two-part name",
        database=None,
        schema="staging",
        name="orders",
        expected_qualified="staging.orders",
    ),
    BuildQualifiedNameTestCase(
        description="name only produces unqualified name",
        database=None,
        schema=None,
        name="orders",
        expected_qualified="orders",
    ),
    BuildQualifiedNameTestCase(
        description="database without schema produces two-part name",
        database="analytics",
        schema=None,
        name="orders",
        expected_qualified="analytics.orders",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    QUALIFIED_NAME_TEST_CASES,
    ids=[case.description for case in QUALIFIED_NAME_TEST_CASES],
)
def test_given_relation_parts_when_building_qualified_name_then_returns_expected(
    test_case: BuildQualifiedNameTestCase,
) -> None:
    result: str = build_qualified_name(
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )

    assert result == test_case.expected_qualified
