"""Tests for shared type helpers."""

from __future__ import annotations

import pytest

from sqlbuild.shared.types import SqlReferenceKind
from tests.unit.src.sqlbuild.shared._test_types import (
    SqlReferenceKindExampleCallTestCase,
)

EXAMPLE_CALL_TEST_CASES: list[SqlReferenceKindExampleCallTestCase] = [
    SqlReferenceKindExampleCallTestCase(
        description="escapes single quotes in single quoted example arguments",
        reference_kind=SqlReferenceKind.REF,
        args=("customer's_orders",),
        quote="'",
        expected_call="__ref('customer''s_orders')",
    ),
    SqlReferenceKindExampleCallTestCase(
        description="escapes double quotes in double quoted example arguments",
        reference_kind=SqlReferenceKind.REF,
        args=('customer"s_orders',),
        quote='"',
        expected_call='__ref("customer""s_orders")',
    ),
    SqlReferenceKindExampleCallTestCase(
        description="formats multiple single quoted example arguments",
        reference_kind=SqlReferenceKind.DBT_REF,
        args=("package_name", "model's_name"),
        quote="'",
        expected_call="__dbt_ref('package_name', 'model''s_name')",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    EXAMPLE_CALL_TEST_CASES,
    ids=[case.description for case in EXAMPLE_CALL_TEST_CASES],
)
def test_given_reference_kind_when_formatting_example_call_then_escapes_arguments(
    test_case: SqlReferenceKindExampleCallTestCase,
) -> None:
    assert (
        test_case.reference_kind.example_call(*test_case.args, quote=test_case.quote)
        == test_case.expected_call
    )
