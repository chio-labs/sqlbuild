"""Tests for typed warehouse-state SQL literals."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from sqlbuild.sql_values.main.render_state_literal import render_state_sql_literal
from sqlbuild.sql_values.types import StateSqlValueType
from tests.unit.src.sqlbuild.sql_values._test_types import StateLiteralGoldenTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        StateLiteralGoldenTestCase(
            description="canonical state literals",
            expected_literals={
                "string": "'O''Reilly'",
                "integer": "CAST(42 AS BIGINT)",
                "boolean_true": "TRUE",
                "boolean_false": "FALSE",
                "timestamp": "CAST('2026-01-01T00:00:00+00:00' AS TIMESTAMP)",
                "date": "CAST('2026-01-01' AS DATE)",
                "json": '\'{"count":2,"quoted":"it\'\'s"}\'',
                "null": "NULL",
                "typed_null": "CAST(NULL AS TIMESTAMP)",
            },
        )
    ],
    ids=lambda case: case.description,
)
def test_given_each_declared_state_type_when_rendering_then_returns_canonical_sql(
    test_case: StateLiteralGoldenTestCase,
) -> None:
    assert {
        "string": render_state_sql_literal(
            value="O'Reilly", declared_type=StateSqlValueType.STRING
        ),
        "integer": render_state_sql_literal(value=42, declared_type=StateSqlValueType.INTEGER),
        "boolean_true": render_state_sql_literal(
            value=True, declared_type=StateSqlValueType.BOOLEAN
        ),
        "boolean_false": render_state_sql_literal(
            value=False, declared_type=StateSqlValueType.BOOLEAN
        ),
        "timestamp": render_state_sql_literal(
            value=datetime(2026, 1, 1, 1, tzinfo=timezone(timedelta(hours=1))),
            declared_type=StateSqlValueType.TIMESTAMP,
        ),
        "date": render_state_sql_literal(
            value=date(2026, 1, 1), declared_type=StateSqlValueType.DATE
        ),
        "json": render_state_sql_literal(
            value={"quoted": "it's", "count": 2}, declared_type=StateSqlValueType.JSON
        ),
        "null": render_state_sql_literal(value=None, declared_type=StateSqlValueType.STRING),
        "typed_null": render_state_sql_literal(
            value=None, declared_type=StateSqlValueType.TIMESTAMP
        ),
    } == test_case.expected_literals


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
