from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import ExpressionInferenceProfile
from sqlbuild.adapter.shared.types import CursorKind, FunctionNullabilityRule
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import (
    FunctionArgument,
    FunctionReturnColumn,
)
from sqlbuild.compiler.lineage.types import InferredNullability
from tests.unit.src.sqlbuild.adapters.duckdb._test_types import (
    DuckDbExpressionInferenceProfileTestCase,
    DuckDbRenderCursorBoundLiteralTestCase,
    DuckDbRenderIdentifierTestCase,
    DuckDbRenderTableFunctionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbExpressionInferenceProfileTestCase(
            description="returns DuckDB inference rules",
            expected_sql_analysis_dialect="duckdb",
            expected_rule_results={"LOWER": InferredNullability.NON_NULL},
        )
    ],
    ids=["returns DuckDB inference rules"],
)
def test_given_duckdb_adapter_when_getting_inference_profile_then_returns_expected_rules(
    test_case: DuckDbExpressionInferenceProfileTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()

    profile: ExpressionInferenceProfile = adapter.expression_inference_profile()

    assert profile.sql_analysis_dialect == test_case.expected_sql_analysis_dialect
    for rule_name, expected in test_case.expected_rule_results.items():
        rule: FunctionNullabilityRule | None = profile.function_nullability_rule(rule_name)
        assert rule is not None
        assert rule((InferredNullability.NON_NULL,)) == expected


TEST_CASES: list[DuckDbRenderCursorBoundLiteralTestCase] = [
    DuckDbRenderCursorBoundLiteralTestCase(
        description="renders timestamp cursor bounds as typed literals",
        value="2024-01-15T00:00:00",
        cursor_type=CursorKind.TIMESTAMP,
        expected_literal="TIMESTAMP '2024-01-15T00:00:00'",
    ),
    DuckDbRenderCursorBoundLiteralTestCase(
        description="renders integer cursor bounds without quotes",
        value="42",
        cursor_type=CursorKind.INTEGER,
        expected_literal="42",
    ),
]

DUCKDB_RENDER_IDENTIFIER_TEST_CASES: list[DuckDbRenderIdentifierTestCase] = [
    DuckDbRenderIdentifierTestCase(
        description="quotes lowercase identifiers without changing case",
        name="event_id",
        expected_identifier='"event_id"',
    ),
    DuckDbRenderIdentifierTestCase(
        description="escapes embedded double quotes",
        name='event"id',
        expected_identifier='"event""id"',
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DUCKDB_RENDER_IDENTIFIER_TEST_CASES,
    ids=[case.description for case in DUCKDB_RENDER_IDENTIFIER_TEST_CASES],
)
def test_given_identifier_when_rendering_then_duckdb_quotes_identifier(
    test_case: DuckDbRenderIdentifierTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()

    identifier: str = adapter.render_identifier(test_case.name)

    assert identifier == test_case.expected_identifier


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_cursor_bounds_when_rendering_then_duckdb_returns_expected_literal(
    test_case: DuckDbRenderCursorBoundLiteralTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()

    result: str = adapter.render_cursor_bound_literal(test_case.value, test_case.cursor_type)

    assert result == test_case.expected_literal


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbRenderTableFunctionTestCase(
            description="renders table function as DuckDB table macro",
            expected_statements=(
                "CREATE OR REPLACE MACRO main.customer_orders(p_customer_id) AS TABLE\n"
                "SELECT order_id FROM main.fact_orders\n"
                "WHERE customer_id = p_customer_id",
            ),
        )
    ],
    ids=["renders table function as DuckDB table macro"],
)
def test_given_table_function_when_rendering_then_duckdb_returns_expected_macro(
    test_case: DuckDbRenderTableFunctionTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        destination="main.customer_orders",
        arguments=(FunctionArgument(name="p_customer_id", type="INTEGER"),),
        returns="TABLE",
        body_sql="SELECT order_id FROM main.fact_orders\nWHERE customer_id = p_customer_id",
        return_columns=(FunctionReturnColumn(name="order_id", type="INTEGER"),),
    )

    assert statements == test_case.expected_statements
