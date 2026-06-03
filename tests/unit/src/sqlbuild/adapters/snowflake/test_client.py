from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    ExpressionInferenceProfile,
    SchemaDiffResult,
    StatementRecorder,
    TableFreshnessMetadata,
)
from sqlbuild.adapter.shared.types import CursorKind, FunctionNullabilityRule
from sqlbuild.adapters.snowflake.client import SnowflakeAdapter
from sqlbuild.compiler.compile.models.core import (
    FunctionArgument,
    FunctionReturnColumn,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.lineage.types import InferredNullability
from tests.unit.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeExpressionInferenceProfileTestCase,
    SnowflakeLoadSeedTestCase,
    SnowflakeMoveOrCopyRelationTestCase,
    SnowflakeQueryColumnNamesTestCase,
    SnowflakeRenderCloneTestCase,
    SnowflakeRenderCursorBoundLiteralTestCase,
    SnowflakeRenderIdentifierTestCase,
    SnowflakeRenderPythonFunctionTestCase,
    SnowflakeRenderTableFunctionTestCase,
    SnowflakeSchemaDiffTestCase,
    SnowflakeTableFreshnessMetadataErrorTestCase,
    SnowflakeTableFreshnessMetadataTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.helpers import (
    FakeSnowflakeDescribeConnection,
    FakeSnowflakeDescribeCursor,
    FakeSnowflakeMetadataConnection,
    FakeSnowflakeMetadataCursor,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeExpressionInferenceProfileTestCase(
            description="returns Snowflake inference rules",
            expected_sqlglot_dialect="snowflake",
            expected_identifier_limit=255,
            expected_rule_results={
                "IFF": InferredNullability.NON_NULL,
                "UPPER": InferredNullability.NON_NULL,
            },
        )
    ],
    ids=["returns Snowflake inference rules"],
)
def test_given_snowflake_adapter_when_getting_inference_profile_then_returns_expected_rules(
    test_case: SnowflakeExpressionInferenceProfileTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    profile: ExpressionInferenceProfile = adapter.expression_inference_profile()

    assert profile.sqlglot_dialect == test_case.expected_sqlglot_dialect
    assert adapter.maximum_identifier_length() == test_case.expected_identifier_limit
    iff_rule: FunctionNullabilityRule | None = profile.function_nullability_rule("IFF")
    upper_rule: FunctionNullabilityRule | None = profile.function_nullability_rule("UPPER")
    assert iff_rule is not None
    assert upper_rule is not None
    assert (
        iff_rule(
            (
                InferredNullability.UNKNOWN,
                InferredNullability.NON_NULL,
                InferredNullability.NON_NULL,
            )
        )
        == test_case.expected_rule_results["IFF"]
    )
    assert upper_rule((InferredNullability.NON_NULL,)) == test_case.expected_rule_results["UPPER"]


TEST_CASES: list[SnowflakeRenderCursorBoundLiteralTestCase] = [
    SnowflakeRenderCursorBoundLiteralTestCase(
        description="renders timestamp cursor bounds as typed literals",
        value="2024-01-15T00:00:00",
        cursor_type=CursorKind.TIMESTAMP,
        expected_literal="TIMESTAMP '2024-01-15T00:00:00'",
    ),
    SnowflakeRenderCursorBoundLiteralTestCase(
        description="renders integer cursor bounds without quotes",
        value="42",
        cursor_type=CursorKind.INTEGER,
        expected_literal="42",
    ),
]

SNOWFLAKE_RENDER_CLONE_TEST_CASES: list[SnowflakeRenderCloneTestCase] = [
    SnowflakeRenderCloneTestCase(
        description="renders zero copy table clone by default",
        source="prod.fact_orders",
        target="dev.fact_orders",
        hard_copy=False,
        expected_statements=("CREATE OR REPLACE TABLE dev.fact_orders CLONE prod.fact_orders",),
        expected_supports_zero_copy=True,
    ),
    SnowflakeRenderCloneTestCase(
        description="renders CTAS when hard copy is requested",
        source="prod.fact_orders",
        target="dev.fact_orders",
        hard_copy=True,
        expected_statements=(
            "CREATE OR REPLACE TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
        ),
        expected_supports_zero_copy=True,
    ),
]

SNOWFLAKE_RENDER_IDENTIFIER_TEST_CASES: list[SnowflakeRenderIdentifierTestCase] = [
    SnowflakeRenderIdentifierTestCase(
        description="uppercases logical lowercase identifiers before quoting",
        name="event_id",
        expected_identifier='"EVENT_ID"',
    ),
    SnowflakeRenderIdentifierTestCase(
        description="escapes quotes after applying Snowflake uppercase semantics",
        name='event"id',
        expected_identifier='"EVENT""ID"',
    ),
]

SNOWFLAKE_TABLE_FRESHNESS_ERROR_TEST_CASES: list[SnowflakeTableFreshnessMetadataErrorTestCase] = [
    SnowflakeTableFreshnessMetadataErrorTestCase(
        description="raises when metadata row is missing",
        row=None,
        expected_error_fragment="not found",
    ),
    SnowflakeTableFreshnessMetadataErrorTestCase(
        description="raises when relation is a view",
        row=("VIEW", datetime(2026, 1, 2, 3, 4, 5)),
        expected_error_fragment="only supports physical tables",
    ),
    SnowflakeTableFreshnessMetadataErrorTestCase(
        description="raises when last altered is missing",
        row=("BASE TABLE", None),
        expected_error_fragment="missing LAST_ALTERED",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_cursor_bounds_when_rendering_then_snowflake_returns_expected_literal(
    test_case: SnowflakeRenderCursorBoundLiteralTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    result: str = adapter.render_cursor_bound_literal(test_case.value, test_case.cursor_type)

    assert result == test_case.expected_literal


@pytest.mark.parametrize(
    "test_case",
    SNOWFLAKE_RENDER_CLONE_TEST_CASES,
    ids=[case.description for case in SNOWFLAKE_RENDER_CLONE_TEST_CASES],
)
def test_given_clone_request_when_rendering_then_snowflake_uses_expected_clone_sql(
    test_case: SnowflakeRenderCloneTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    statements: tuple[str, ...] = adapter.render_clone(
        source=test_case.source,
        target=test_case.target,
        hard_copy=test_case.hard_copy,
    )

    assert adapter.supports_zero_copy_clone() is test_case.expected_supports_zero_copy
    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeMoveOrCopyRelationTestCase(
            description="moves table across schemas with native rename",
            source="ANALYTICS.MARTS.FACT_ORDERS",
            target="ANALYTICS.MARTS__SQB_PHYSICAL.FACT_ORDERS__V_ABC123",
            expected_statements=(
                "ALTER TABLE ANALYTICS.MARTS.FACT_ORDERS "
                "RENAME TO ANALYTICS.MARTS__SQB_PHYSICAL.FACT_ORDERS__V_ABC123",
            ),
        )
    ],
    ids=["moves table across schemas with native rename"],
)
def test_given_cross_schema_table_move_when_moving_then_snowflake_uses_native_rename(
    test_case: SnowflakeMoveOrCopyRelationTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeDescribeCursor = FakeSnowflakeDescribeCursor(())
    connection: FakeSnowflakeDescribeConnection = FakeSnowflakeDescribeConnection(cursor)
    statement_recorder: StatementRecorder = StatementRecorder()

    adapter.move_or_copy_relation(
        connection,
        source=test_case.source,
        target=test_case.target,
        remove_source=True,
        allow_copy_fallback=False,
        statement_recorder=statement_recorder,
    )

    assert tuple(connection.executed_sql) == test_case.expected_statements
    assert tuple(event.content for event in statement_recorder.snapshot()) == (
        test_case.expected_statements
    )


@pytest.mark.parametrize(
    "test_case",
    SNOWFLAKE_RENDER_IDENTIFIER_TEST_CASES,
    ids=[case.description for case in SNOWFLAKE_RENDER_IDENTIFIER_TEST_CASES],
)
def test_given_identifier_when_rendering_then_snowflake_quotes_uppercase_identifier(
    test_case: SnowflakeRenderIdentifierTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    identifier: str = adapter.render_identifier(test_case.name)

    assert identifier == test_case.expected_identifier


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeTableFreshnessMetadataTestCase(
            description="returns last altered for physical table",
            row=("BASE TABLE", datetime(2026, 1, 2, 3, 4, 5)),
            expected_data_version=datetime(2026, 1, 2, 3, 4, 5),
            expected_value_kind="timestamp",
            expected_supports_metadata=True,
        )
    ],
    ids=["returns last altered for physical table"],
)
def test_given_physical_table_when_getting_freshness_metadata_then_returns_last_altered(
    test_case: SnowflakeTableFreshnessMetadataTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(test_case.row)
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(cursor)

    metadata: TableFreshnessMetadata = adapter.get_table_freshness_metadata(
        connection,
        database="ANALYTICS",
        schema="RAW",
        name="ORDERS",
    )

    assert adapter.supports_table_freshness_metadata() is test_case.expected_supports_metadata
    assert metadata.data_version == test_case.expected_data_version
    assert metadata.value_kind == test_case.expected_value_kind
    assert metadata.observed_at == test_case.expected_data_version
    assert cursor.executed_sql is not None
    assert "information_schema.tables" in cursor.executed_sql
    assert "last_altered" in cursor.executed_sql
    assert cursor.executed_params == ("ORDERS", "RAW", "ANALYTICS")
    assert cursor.closed is True


@pytest.mark.parametrize(
    "test_case",
    SNOWFLAKE_TABLE_FRESHNESS_ERROR_TEST_CASES,
    ids=[case.description for case in SNOWFLAKE_TABLE_FRESHNESS_ERROR_TEST_CASES],
)
def test_given_unsupported_relation_when_getting_freshness_metadata_then_raises_clear_error(
    test_case: SnowflakeTableFreshnessMetadataErrorTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeMetadataCursor = FakeSnowflakeMetadataCursor(test_case.row)
    connection: FakeSnowflakeMetadataConnection = FakeSnowflakeMetadataConnection(cursor)

    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        adapter.get_table_freshness_metadata(
            connection,
            database="ANALYTICS",
            schema="RAW",
            name="ORDERS",
        )

    assert cursor.closed is True


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRenderPythonFunctionTestCase(
            description="renders Python UDF DDL with runtime handler and packages",
            expected_sql=(
                "CREATE OR REPLACE FUNCTION "
                "udf_db.udf_schema.is_positive_int(a_string STRING)\n"
                "RETURNS INTEGER\n"
                "LANGUAGE PYTHON\n"
                "RUNTIME_VERSION = '3.11'\n"
                "HANDLER = 'main'\n"
                "PACKAGES = ('numpy','pandas==1.5.0')\n"
                "AS $$\n"
                "def main(a_string):\n"
                "    return 1 if a_string else 0\n"
                "$$"
            ),
        )
    ],
    ids=["renders Python UDF DDL with runtime handler and packages"],
)
def test_given_python_function_when_rendering_then_snowflake_returns_expected_ddl(
    test_case: SnowflakeRenderPythonFunctionTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        target="udf_db.udf_schema.is_positive_int",
        arguments=(FunctionArgument(name="a_string", type="STRING"),),
        returns="INTEGER",
        body_sql="def main(a_string):\n    return 1 if a_string else 0",
        language=FunctionLanguage.PYTHON,
        runtime_version="3.11",
        entry_point="main",
        packages=("numpy", "pandas==1.5.0"),
    )

    assert statements == (test_case.expected_sql,)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRenderTableFunctionTestCase(
            description="renders table function DDL with explicit Snowflake return columns",
            expected_sql=(
                "CREATE OR REPLACE FUNCTION analytics.customer_orders(p_customer_id INTEGER)\n"
                "RETURNS TABLE (order_id INTEGER)\n"
                "AS $$\nSELECT order_id FROM analytics.fact_orders\n"
                "WHERE customer_id = p_customer_id\n$$"
            ),
        )
    ],
    ids=["renders table function DDL with explicit Snowflake return columns"],
)
def test_given_table_function_when_rendering_then_snowflake_returns_expected_ddl(
    test_case: SnowflakeRenderTableFunctionTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        target="analytics.customer_orders",
        arguments=(FunctionArgument(name="p_customer_id", type="INTEGER"),),
        returns="TABLE",
        body_sql=("SELECT order_id FROM analytics.fact_orders\nWHERE customer_id = p_customer_id"),
        return_columns=(FunctionReturnColumn(name="order_id", type="INTEGER"),),
    )

    assert statements == (test_case.expected_sql,)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeSchemaDiffTestCase(
            description="treats semantically equivalent numeric types as unchanged",
            expected_result=SchemaDiffResult(),
        )
    ],
    ids=["treats semantically equivalent numeric types as unchanged"],
)
def test_given_equivalent_types_when_diffing_schema_then_snowflake_ignores_alias_only_changes(
    test_case: SnowflakeSchemaDiffTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    monkeypatch.setattr(
        adapter,
        "describe_relation",
        lambda connection, relation: (
            (ColumnInfo(name="id", type="NUMBER(38,0)"),)
            if relation == "left_relation"
            else (ColumnInfo(name="id", type="DECIMAL(38,0)"),)
        ),
    )

    result: SchemaDiffResult = adapter.diff_schema(
        connection=object(),
        left="left_relation",
        right="right_relation",
    )

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeQueryColumnNamesTestCase(
            description="preserves Snowflake cursor output column names",
            cursor_description=(("ID",), ("FIRST_NAME",), ("CREATED_AT",)),
            expected_columns=("ID", "FIRST_NAME", "CREATED_AT"),
        ),
    ],
    ids=["preserves Snowflake cursor output column names"],
)
def test_given_snowflake_query_metadata_when_getting_column_names_then_preserves_cursor_names(
    test_case: SnowflakeQueryColumnNamesTestCase,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeDescribeCursor = FakeSnowflakeDescribeCursor(
        description=test_case.cursor_description
    )
    connection: FakeSnowflakeDescribeConnection = FakeSnowflakeDescribeConnection(cursor)

    columns: tuple[str, ...] = adapter.query_column_names(
        connection=connection,
        sql="SELECT 1 AS id, 'Ada' AS first_name, CURRENT_TIMESTAMP AS created_at",
    )

    assert columns == test_case.expected_columns
    assert cursor.closed is True


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeLoadSeedTestCase(
            description="loads seed with default quote character",
            csv_text='id,name\n1,"Liege waffle"\n',
            expected_rows=[("1", "Liege waffle")],
        ),
    ],
    ids=["loads seed with default quote character"],
)
def test_given_default_seed_csv_settings_when_loading_seed_then_uses_python_csv_defaults(
    test_case: SnowflakeLoadSeedTestCase,
    tmp_path: Path,
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()
    cursor: FakeSnowflakeDescribeCursor = FakeSnowflakeDescribeCursor(description=())
    connection: FakeSnowflakeDescribeConnection = FakeSnowflakeDescribeConnection(cursor)
    seed_file: Path = tmp_path / "waffle_types.csv"
    seed_file.write_text(test_case.csv_text, encoding="utf-8")

    adapter.load_seed(
        connection,
        target="dev.waffle_types",
        file_path=seed_file,
        columns=(
            ColumnInfo(name="id", type="INTEGER"),
            ColumnInfo(name="name", type="VARCHAR"),
        ),
        replace=False,
        statement_recorder=StatementRecorder(),
    )

    assert cursor.executemany_rows == test_case.expected_rows
