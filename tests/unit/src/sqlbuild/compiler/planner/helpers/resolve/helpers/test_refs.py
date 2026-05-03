"""Tests for ref reference resolution."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledRelationTarget
from sqlbuild.compiler.planner.helpers.resolve.helpers.refs import (
    resolve_dbt_ref_references,
    resolve_ref_references,
)
from sqlbuild.compiler.planner.models import CursorBounds
from tests.unit.src.sqlbuild.compiler.planner.helpers.resolve.helpers._test_types import (
    RefResolutionTestCase,
)

_MODEL_TARGETS: dict[str, CompiledRelationTarget] = {
    "orders": CompiledRelationTarget(
        database=None, schema="staging", name="orders", qualified_name="staging.orders"
    ),
    "customers": CompiledRelationTarget(
        database=None, schema="staging", name="customers", qualified_name="staging.customers"
    ),
}

_SEED_TARGETS: dict[str, CompiledRelationTarget] = {
    "country_codes": CompiledRelationTarget(
        database=None, schema="seeds", name="country_codes", qualified_name="seeds.country_codes"
    ),
}

NO_CURSOR_TEST_CASES: list[RefResolutionTestCase] = [
    RefResolutionTestCase(
        description="replaces ref with qualified name",
        query_sql='SELECT * FROM __ref("orders")',
        expected_sql="SELECT * FROM staging.orders",
    ),
    RefResolutionTestCase(
        description="replaces multiple refs in one query",
        query_sql=(
            'SELECT a.*, b.* FROM __ref("orders") a JOIN __ref("customers") b ON a.id = b.id'
        ),
        expected_sql=(
            "SELECT a.*, b.* FROM staging.orders a JOIN staging.customers b ON a.id = b.id"
        ),
    ),
    RefResolutionTestCase(
        description="leaves unknown ref unchanged",
        query_sql='SELECT * FROM __ref("unknown_model")',
        expected_sql='SELECT * FROM __ref("unknown_model")',
    ),
    RefResolutionTestCase(
        description="resolves seed ref from seed targets",
        query_sql='SELECT * FROM __ref("country_codes")',
        expected_sql="SELECT * FROM seeds.country_codes",
    ),
]

WITH_CURSOR_TEST_CASES: list[RefResolutionTestCase] = [
    RefResolutionTestCase(
        description="wraps ref in cursor-filtered subquery",
        query_sql='SELECT * FROM __ref("orders")',
        expected_sql=(
            "SELECT * FROM (SELECT * FROM staging.orders"
            " WHERE event_time >= '2024-01-15'"
            " AND event_time < '2024-02-01')"
        ),
    ),
    RefResolutionTestCase(
        description="only wraps refs that have cursor inputs",
        query_sql=(
            'SELECT a.*, b.* FROM __ref("orders") a JOIN __ref("customers") b ON a.id = b.id'
        ),
        expected_sql=(
            "SELECT a.*, b.* FROM (SELECT * FROM staging.orders"
            " WHERE event_time >= '2024-01-15'"
            " AND event_time < '2024-02-01') a "
            "JOIN staging.customers b ON a.id = b.id"
        ),
    ),
]

_CURSOR_BOUNDS: CursorBounds = CursorBounds(start="2024-01-15", end="2024-02-01")
_CURSOR_INPUTS: dict[str, str] = {"orders": "event_time"}


@pytest.mark.parametrize(
    "test_case",
    NO_CURSOR_TEST_CASES,
    ids=[case.description for case in NO_CURSOR_TEST_CASES],
)
def test_given_refs_without_cursor_when_resolving_then_returns_expected_sql(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_ref_references(
        query_sql=test_case.query_sql,
        model_targets=_MODEL_TARGETS,
        seed_targets=_SEED_TARGETS,
        cursor_bounds=None,
        cursor_inputs={},
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    WITH_CURSOR_TEST_CASES,
    ids=[case.description for case in WITH_CURSOR_TEST_CASES],
)
def test_given_refs_with_cursor_when_resolving_then_returns_expected_sql(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_ref_references(
        query_sql=test_case.query_sql,
        model_targets=_MODEL_TARGETS,
        seed_targets=_SEED_TARGETS,
        cursor_bounds=_CURSOR_BOUNDS,
        cursor_inputs=_CURSOR_INPUTS,
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        RefResolutionTestCase(
            description="leaves dbt ref unchanged as stub",
            query_sql='SELECT * FROM __dbt_ref("external_model")',
            expected_sql='SELECT * FROM __dbt_ref("external_model")',
        ),
    ],
    ids=["leaves dbt ref unchanged as stub"],
)
def test_given_dbt_ref_when_resolving_then_leaves_unchanged(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_dbt_ref_references(query_sql=test_case.query_sql)

    assert result == test_case.expected_sql
