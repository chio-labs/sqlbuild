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
from tests.unit.src.sqlbuild.adapter.base.helpers import RecordingConnection
from tests.unit.src.sqlbuild.adapters.duckdb._test_types import (
    DuckDbExpressionInferenceProfileTestCase,
    DuckDbMetadataSqlTestCase,
    DuckDbPruneSqlTestCase,
    DuckDbRelationMaxCursorTestCase,
    DuckDbRenderCursorBoundLiteralTestCase,
    DuckDbRenderIdentifierTestCase,
    DuckDbRenderSwapTestCase,
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
        DuckDbRelationMaxCursorTestCase(
            description="returns max cursor from populated relation and none from empty relation",
            expected_populated_value=7,
            expected_empty_value=None,
        )
    ],
    ids=["returns max cursor from populated relation and none from empty relation"],
)
def test_given_duckdb_relation_when_getting_max_cursor_then_returns_relation_max(
    test_case: DuckDbRelationMaxCursorTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: object = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, 'CREATE TABLE events ("event""time" INTEGER)')
        adapter.execute(connection, "INSERT INTO events VALUES (1), (7), (3)")
        adapter.execute(connection, 'CREATE TABLE empty_events ("event""time" INTEGER)')

        populated_value: object | None = adapter.get_relation_max_cursor(
            connection,
            relation="events",
            cursor_column='event"time',
        )
        empty_value: object | None = adapter.get_relation_max_cursor(
            connection,
            relation="empty_events",
            cursor_column='event"time',
        )
    finally:
        adapter.close(connection)

    assert populated_value == test_case.expected_populated_value
    assert empty_value == test_case.expected_empty_value


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


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbPruneSqlTestCase(
            description="renders fingerprint history pruning with rowid window delete",
            database=None,
            schema="analytics",
            retain_versions=5,
            expected_fragments=(
                "DELETE FROM analytics._sqlbuild_fingerprints WHERE rowid IN",
                "ROW_NUMBER() OVER",
                "PARTITION BY node_type, node_name",
                "ORDER BY ts DESC, run_id DESC",
                "__sqlbuild_history_rank > 5",
            ),
        )
    ],
    ids=["renders fingerprint history pruning with rowid window delete"],
)
def test_given_fingerprint_table_when_rendering_prune_then_duckdb_uses_history_rank(
    test_case: DuckDbPruneSqlTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()

    sql: str = adapter.render_prune_fingerprint_history_sql(
        database=test_case.database,
        schema=test_case.schema,
        retain_versions=test_case.retain_versions,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in sql


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbPruneSqlTestCase(
            description="renders source freshness history pruning with full identity",
            database=None,
            schema="analytics",
            retain_versions=3,
            expected_fragments=(
                "DELETE FROM analytics._sqlbuild_source_freshness WHERE rowid IN",
                "ROW_NUMBER() OVER",
                "PARTITION BY source_name, target_database, target_schema, target_name",
                "ORDER BY observed_at DESC, run_id DESC",
                "__sqlbuild_history_rank > 3",
            ),
        )
    ],
    ids=["renders source freshness history pruning with full identity"],
)
def test_given_source_freshness_table_when_rendering_prune_then_duckdb_uses_history_rank(
    test_case: DuckDbPruneSqlTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()

    sql: str = adapter.render_prune_source_freshness_history_sql(
        database=test_case.database,
        schema=test_case.schema,
        retain_versions=test_case.retain_versions,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in sql


@pytest.mark.parametrize(
    "test_case",
    [
        DuckDbMetadataSqlTestCase(
            description="escapes single quotes in DuckDB metadata SQL literals",
            database="warehouse'prod",
            schema="sales'ops",
            name="orders'2026",
            expected_sql=(
                "SELECT 1 FROM information_schema.schemata "
                "WHERE schema_name = 'sales''ops' AND catalog_name = 'warehouse''prod'",
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_name = 'orders''2026' "
                "AND table_schema = 'sales''ops' AND table_catalog = 'warehouse''prod'",
                "SELECT table_name, table_schema, table_type "
                "FROM information_schema.tables WHERE 1=1 "
                "AND table_schema IN ('sales''ops') "
                "AND table_name IN ('orders''2026') AND table_catalog = 'warehouse''prod'",
                "SELECT function_name, schema_name, function_type "
                "FROM duckdb_functions() WHERE 1=1 "
                "AND schema_name IN ('sales''ops') "
                "AND function_name IN ('orders''2026') AND database_name = 'warehouse''prod'",
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'orders''2026' "
                "AND table_schema = 'sales''ops' AND table_catalog = 'warehouse''prod' "
                "ORDER BY ordinal_position",
                "SELECT table_name, column_name, data_type "
                "FROM information_schema.columns WHERE 1=1 "
                "AND table_schema IN ('sales''ops') "
                "AND table_name IN ('orders''2026') AND table_catalog = 'warehouse''prod' "
                "ORDER BY table_name, ordinal_position",
            ),
        )
    ],
    ids=["escapes single quotes in DuckDB metadata SQL literals"],
)
def test_given_metadata_names_with_quotes_when_querying_then_duckdb_escapes_literals(
    test_case: DuckDbMetadataSqlTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: RecordingConnection = RecordingConnection()

    adapter.schema_exists(connection, database=test_case.database, schema=test_case.schema)
    adapter.relation_exists(
        connection,
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )
    adapter.list_relations(
        connection,
        database=test_case.database,
        schemas=(test_case.schema,),
        names=(test_case.name,),
    )
    adapter.list_functions(
        connection,
        database=test_case.database,
        schemas=(test_case.schema,),
        names=(test_case.name,),
    )
    adapter.get_columns(
        connection,
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )
    adapter.get_all_columns(
        connection,
        database=test_case.database,
        schemas=(test_case.schema,),
        names=(test_case.name,),
    )

    assert tuple(connection.executed_sql) == test_case.expected_sql


RENDER_SWAP_TEST_CASES: tuple[DuckDbRenderSwapTestCase, ...] = (
    DuckDbRenderSwapTestCase(
        description="renders swap for unquoted qualified relations",
        left="dev_marts.agg_daily_revenue",
        right="dev_marts.agg_daily_revenue__stage",
        expected_statements=(
            'ALTER TABLE dev_marts.agg_daily_revenue RENAME TO "agg_daily_revenue__swap_staging"',
            "ALTER TABLE dev_marts.agg_daily_revenue__stage RENAME TO agg_daily_revenue",
            'ALTER TABLE dev_marts."agg_daily_revenue__swap_staging" '
            "RENAME TO agg_daily_revenue__stage",
        ),
    ),
    DuckDbRenderSwapTestCase(
        description="renders swap for quoted qualified relations",
        left='"dev_marts"."agg_daily_revenue"',
        right='"dev_marts"."agg_daily_revenue__stage"',
        expected_statements=(
            'ALTER TABLE "dev_marts"."agg_daily_revenue" '
            'RENAME TO "agg_daily_revenue__swap_staging"',
            'ALTER TABLE "dev_marts"."agg_daily_revenue__stage" RENAME TO "agg_daily_revenue"',
            'ALTER TABLE "dev_marts"."agg_daily_revenue__swap_staging" '
            'RENAME TO "agg_daily_revenue__stage"',
        ),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    RENDER_SWAP_TEST_CASES,
    ids=[case.description for case in RENDER_SWAP_TEST_CASES],
)
def test_given_qualified_relations_when_rendering_swap_then_keeps_staging_in_schema(
    test_case: DuckDbRenderSwapTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()

    statements: tuple[str, ...] = adapter.render_swap(left=test_case.left, right=test_case.right)

    assert statements == test_case.expected_statements
