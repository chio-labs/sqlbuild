"""Behavior tests for lazy common SQL facts."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from sqlbuild.rule_engine.classes.sql_document import SqlDocument
from tests.unit.src.sqlbuild.rule_engine.classes.sql_document._test_types import (
    SqlDocumentTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlDocumentTestCase(
            description="CTE and star facts are projected from Polyglot",
            source="WITH orders AS (SELECT * FROM raw_orders) SELECT * FROM orders",
            expected_cte_count=1,
            expected_star_count=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_common_sql_structures_when_projecting_then_typed_counts_match(
    test_case: SqlDocumentTestCase,
) -> None:
    document: SqlDocument = SqlDocument(source=test_case.source, dialect="duckdb")

    assert len(document.ctes()) == test_case.expected_cte_count
    assert len(document.star_projections()) == test_case.expected_star_count


@pytest.mark.parametrize(
    "test_case",
    [
        SqlDocumentTestCase(
            description="Polyglot loading is deferred until AST access",
            source="SELECT 1 AS order_id",
            expected_cte_count=0,
            expected_star_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_new_sql_document_when_not_accessing_ast_then_polyglot_is_not_loaded(
    test_case: SqlDocumentTestCase,
) -> None:
    with patch("sqlbuild.rule_engine.classes.sql_document.import_polyglot_sql") as import_polyglot:
        _ = SqlDocument(source=test_case.source, dialect="duckdb")

    assert import_polyglot.call_count == test_case.expected_cte_count
