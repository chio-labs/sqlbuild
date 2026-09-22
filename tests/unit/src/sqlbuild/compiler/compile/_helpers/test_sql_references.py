"""Tests for native-assisted logical SQL reference extraction."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.compiler.references.types import SqlReferenceKind
from tests.unit.src.sqlbuild.compiler.compile._helpers._test_types import (
    SqlReferenceExtractionErrorTestCase,
    SqlReferenceExtractionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlReferenceExtractionTestCase(
            description="simple references preserve authored order",
            sql=(
                "SELECT * FROM __source('orders') "
                'UNION ALL SELECT * FROM __dbt_ref("shop", "customers")'
            ),
            expected_references=(
                (SqlReferenceKind.SOURCE, "orders", None),
                (SqlReferenceKind.DBT_REF, "customers", "shop"),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_simple_references_when_extracting_then_returns_authored_order(
    test_case: SqlReferenceExtractionTestCase,
) -> None:
    references: tuple[CompileSqlReference, ...] = extract_sql_references(test_case.sql)

    assert (
        tuple(
            (reference.ref_kind, reference.ref_name, reference.ref_package)
            for reference in references
        )
        == test_case.expected_references
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SqlReferenceExtractionErrorTestCase(
            description="unclosed reference parenthesis preserves diagnostic",
            sql='SELECT * FROM __ref("orders"',
            expected_error="unclosed parenthesis",
        ),
        SqlReferenceExtractionErrorTestCase(
            description="expression reference name preserves diagnostic",
            sql="SELECT * FROM __ref(concat('ord', 'ers'))",
            expected_error="name argument must be a quoted string or identifier",
        ),
        SqlReferenceExtractionErrorTestCase(
            description="unclosed block comment preserves diagnostic",
            sql='SELECT * FROM __ref("orders") /* unterminated',
            expected_error="unclosed block comment",
        ),
        SqlReferenceExtractionErrorTestCase(
            description="unclosed quoted string preserves diagnostic",
            sql='SELECT * FROM __ref("orders") WHERE note = \'unterminated',
            expected_error="unclosed quoted string",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_reference_sql_when_extracting_then_preserves_python_diagnostic(
    test_case: SqlReferenceExtractionErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error):
        extract_sql_references(test_case.sql)
