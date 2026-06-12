"""Tests for relation naming helpers."""

from __future__ import annotations

import pytest

from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import (
    BuildQualifiedNameTestCase,
)
from tests.unit.src.sqlbuild.executor.run.helpers.helpers import build_name_test_adapter

QUALIFIED_NAME_TEST_CASES: list[BuildQualifiedNameTestCase] = [
    BuildQualifiedNameTestCase(
        description="database and schema and name produces three-part name",
        adapter_name="duckdb",
        database="analytics",
        schema="staging",
        name="orders",
        expected_qualified="analytics.staging.orders",
    ),
    BuildQualifiedNameTestCase(
        description="schema and name without database produces two-part name",
        adapter_name="duckdb",
        database=None,
        schema="staging",
        name="orders",
        expected_qualified="staging.orders",
    ),
    BuildQualifiedNameTestCase(
        description="name only produces unqualified name",
        adapter_name="duckdb",
        database=None,
        schema=None,
        name="orders",
        expected_qualified="orders",
    ),
    BuildQualifiedNameTestCase(
        description="database without schema produces two-part name",
        adapter_name="duckdb",
        database="analytics",
        schema=None,
        name="orders",
        expected_qualified="orders",
    ),
    BuildQualifiedNameTestCase(
        description="bigquery quotes delta relation names with project and dataset",
        adapter_name="bigquery",
        database="example-project",
        schema="dev",
        name="orders__delta",
        expected_qualified="`example-project.dev.orders__delta`",
    ),
    BuildQualifiedNameTestCase(
        description="bigquery quotes fingerprint table names separately from model locations",
        adapter_name="bigquery",
        database="example-project",
        schema="dev",
        name="_sqlbuild_fingerprints",
        expected_qualified="`example-project.dev._sqlbuild_fingerprints`",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    QUALIFIED_NAME_TEST_CASES,
    ids=[case.description for case in QUALIFIED_NAME_TEST_CASES],
)
def test_given_relation_parts_when_resolving_qualified_name_then_returns_expected(
    test_case: BuildQualifiedNameTestCase,
) -> None:
    result: str = resolve_qualified_name_parts(
        adapter=build_name_test_adapter(test_case.adapter_name),
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )

    assert result == test_case.expected_qualified
