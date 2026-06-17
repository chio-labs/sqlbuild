from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    ExpressionInferenceProfile,
    QueryResult,
    RowDiffResult,
    RowDiffSampleCell,
    RowDiffSampleRow,
    SchemaDiffResult,
    StatementRecorder,
    TableFreshnessMetadata,
    TableFreshnessRequest,
)
from sqlbuild.adapter.shared.types import FunctionNullabilityRule
from sqlbuild.adapters.snowflake.client import SnowflakeAdapter
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.executor.run.helpers.reuse import create_relation_from_reuse_origin
from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from sqlbuild.virtual.freshness.main.state_record import source_freshness_record_from_observation
from sqlbuild.virtual.freshness.models import SourceFreshnessObservation
from tests.integration.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeBuildFlowTestCase,
    SnowflakeExpressionNullabilityRuleTestCase,
    SnowflakeMergeTestCase,
    SnowflakeQueryTestCase,
    SnowflakeRelationReuseCopyTestCase,
    SnowflakeRowDiffSampleTestCase,
    SnowflakeRowDiffTestCase,
    SnowflakeSchemaDiffTestCase,
    SnowflakeSchemaIntrospectionTestCase,
    SnowflakeTableFreshnessMetadataTestCase,
)
from tests.integration.src.sqlbuild.adapters.snowflake.helpers import (
    build_statement_recorder,
    execute_statements,
    fetch_rows,
    qualified_name,
    write_seed_file,
)

EXPRESSION_NULLABILITY_RULE_TEST_CASES: list[SnowflakeExpressionNullabilityRuleTestCase] = [
    SnowflakeExpressionNullabilityRuleTestCase(
        description="UPPER preserves non-null literal",
        function_name="UPPER",
        sql_expression="UPPER('ready')",
        rule_args=(InferredNullability.NON_NULL,),
        expected_nullability=InferredNullability.NON_NULL,
        expected_is_null=False,
    ),
    SnowflakeExpressionNullabilityRuleTestCase(
        description="UPPER preserves nullable input",
        function_name="UPPER",
        sql_expression="UPPER(CAST(NULL AS VARCHAR))",
        rule_args=(InferredNullability.NULLABLE,),
        expected_nullability=InferredNullability.NULLABLE,
        expected_is_null=True,
    ),
    SnowflakeExpressionNullabilityRuleTestCase(
        description="IFF with non-null result branches is non-null",
        function_name="IFF",
        sql_expression="IFF(TRUE, 'yes', 'no')",
        rule_args=(
            InferredNullability.UNKNOWN,
            InferredNullability.NON_NULL,
            InferredNullability.NON_NULL,
        ),
        expected_nullability=InferredNullability.NON_NULL,
        expected_is_null=False,
    ),
    SnowflakeExpressionNullabilityRuleTestCase(
        description="IFF with nullable result branch can be null",
        function_name="IFF",
        sql_expression="IFF(TRUE, CAST(NULL AS VARCHAR), 'no')",
        rule_args=(
            InferredNullability.UNKNOWN,
            InferredNullability.NULLABLE,
            InferredNullability.NON_NULL,
        ),
        expected_nullability=InferredNullability.NULLABLE,
        expected_is_null=True,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    EXPRESSION_NULLABILITY_RULE_TEST_CASES,
    ids=[case.description for case in EXPRESSION_NULLABILITY_RULE_TEST_CASES],
)
def test_given_expression_rule_when_querying_then_snowflake_matches_nullability_expectation(
    test_case: SnowflakeExpressionNullabilityRuleTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
) -> None:
    profile: ExpressionInferenceProfile = adapter.expression_inference_profile()
    rule: FunctionNullabilityRule | None = profile.function_nullability_rule(
        test_case.function_name
    )
    assert rule is not None

    result: QueryResult = adapter.query(
        connection,
        f"SELECT {test_case.sql_expression} IS NULL AS is_null",
        limit=None,
    )

    assert rule(test_case.rule_args) == test_case.expected_nullability
    assert result.rows == ((test_case.expected_is_null,),)


QUERY_TEST_CASES: list[SnowflakeQueryTestCase] = [
    SnowflakeQueryTestCase(
        description="returns rows and truncation for limited query",
        sql=(
            "SELECT * FROM ("
            "SELECT 1 AS id, 'alice' AS name UNION ALL "
            "SELECT 2 AS id, 'bob' AS name"
            ") ORDER BY id"
        ),
        limit=1,
        expected_result=QueryResult(
            columns=("ID", "NAME"),
            rows=((1, "alice"),),
            truncated=True,
        ),
    ),
    SnowflakeQueryTestCase(
        description="returns ok result for ddl query",
        sql="CREATE OR REPLACE TEMP TABLE __sqb_query_temp (id INTEGER)",
        limit=20,
        expected_result=QueryResult(),
    ),
]


ROW_DIFF_TEST_CASES: list[SnowflakeRowDiffTestCase] = [
    SnowflakeRowDiffTestCase(
        description="detects equal unequal and side-only rows",
        left_sql=(
            "CREATE OR REPLACE TABLE left_t AS "
            "SELECT * FROM ("
            "SELECT 1 AS id, 'a' AS val UNION ALL "
            "SELECT 2 AS id, 'b' AS val UNION ALL "
            "SELECT 3 AS id, 'c' AS val"
            ")"
        ),
        right_sql=(
            "CREATE OR REPLACE TABLE right_t AS "
            "SELECT * FROM ("
            "SELECT 1 AS id, 'a' AS val UNION ALL "
            "SELECT 2 AS id, 'x' AS val UNION ALL "
            "SELECT 4 AS id, 'd' AS val"
            ")"
        ),
        unique_key="id",
        expected_result=RowDiffResult(
            left_count=3,
            right_count=3,
            joined_count=4,
            equal_count=1,
            unequal_count=1,
            left_only_count=1,
            right_only_count=1,
        ),
    ),
    SnowflakeRowDiffTestCase(
        description="counts equal rows for identical tables",
        left_sql=("CREATE OR REPLACE TABLE left_t AS SELECT * FROM (SELECT 1 AS id, 10 AS amount)"),
        right_sql=(
            "CREATE OR REPLACE TABLE right_t AS SELECT * FROM (SELECT 1 AS id, 10 AS amount)"
        ),
        unique_key="id",
        expected_result=RowDiffResult(
            left_count=1,
            right_count=1,
            joined_count=1,
            equal_count=1,
            unequal_count=0,
            left_only_count=0,
            right_only_count=0,
        ),
    ),
]

ROW_DIFF_SAMPLE_TEST_CASES: list[SnowflakeRowDiffSampleTestCase] = [
    SnowflakeRowDiffSampleTestCase(
        description="returns unequal row samples for changed values",
        left_sql=(
            "CREATE OR REPLACE TABLE left_t AS "
            "SELECT * FROM (SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2 AS id, 'b' AS val)"
        ),
        right_sql=(
            "CREATE OR REPLACE TABLE right_t AS "
            "SELECT * FROM (SELECT 1 AS id, 'x' AS val UNION ALL SELECT 2 AS id, 'b' AS val)"
        ),
        unique_key="id",
        side="left",
        expected_unequal_samples=(
            RowDiffSampleRow(
                key_values=(("id", 1),),
                changed_cells=(RowDiffSampleCell(name="val", left_value="a", right_value="x"),),
            ),
        ),
    ),
    SnowflakeRowDiffSampleTestCase(
        description="returns side only key samples",
        left_sql=(
            "CREATE OR REPLACE TABLE left_t AS "
            "SELECT * FROM (SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2 AS id, 'b' AS val)"
        ),
        right_sql=(
            "CREATE OR REPLACE TABLE right_t AS "
            "SELECT * FROM (SELECT 2 AS id, 'b' AS val UNION ALL SELECT 3 AS id, 'c' AS val)"
        ),
        unique_key="id",
        side="left",
        expected_side_only_samples=((("id", 1),),),
    ),
]

SCHEMA_DIFF_TEST_CASES: list[SnowflakeSchemaDiffTestCase] = [
    SnowflakeSchemaDiffTestCase(
        description="detects added removed and changed column types",
        left_sql=("CREATE OR REPLACE TABLE left_t (id NUMBER, status VARCHAR, old_col BOOLEAN)"),
        right_sql=("CREATE OR REPLACE TABLE right_t (id VARCHAR, status VARCHAR, new_col DATE)"),
        expected_result=SchemaDiffResult(
            added_columns=(ColumnInfo(name="new_col", type="DATE"),),
            removed_columns=(ColumnInfo(name="old_col", type="BOOLEAN"),),
            type_changed_columns=(
                (
                    ColumnInfo(name="id", type="NUMBER(38,0)"),
                    ColumnInfo(name="id", type="VARCHAR(16777216)"),
                ),
            ),
        ),
    ),
    SnowflakeSchemaDiffTestCase(
        description="ignores equivalent scalar aliases and detects numeric scale changes",
        left_sql=(
            "CREATE OR REPLACE TABLE left_t ("
            "id NUMBER(38,0), status VARCHAR, amount NUMBER(10,2), widened NUMBER(10,2))"
        ),
        right_sql=(
            "CREATE OR REPLACE TABLE right_t ("
            "id DECIMAL(38,0), status TEXT, amount DECIMAL(10,2), widened DECIMAL(10,3))"
        ),
        expected_result=SchemaDiffResult(
            type_changed_columns=(
                (
                    ColumnInfo(name="widened", type="NUMBER(10,2)"),
                    ColumnInfo(name="widened", type="NUMBER(10,3)"),
                ),
            ),
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    QUERY_TEST_CASES,
    ids=[case.description for case in QUERY_TEST_CASES],
)
def test_given_sql_when_querying_then_returns_expected_result(
    test_case: SnowflakeQueryTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
) -> None:
    result: QueryResult = adapter.query(connection, test_case.sql, limit=test_case.limit)

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeSchemaIntrospectionTestCase(
            description="discovers created table and view metadata",
            setup_sql=(
                "CREATE OR REPLACE TABLE orders (id NUMBER, amount NUMBER(10,2))",
                "CREATE OR REPLACE VIEW orders_view AS SELECT id, amount FROM orders",
            ),
            expected_relation_exists=True,
            expected_schema_exists=True,
            expected_relation_names=("orders", "orders_view"),
            expected_columns=(
                ColumnInfo(name="id", type="NUMBER(38,0)"),
                ColumnInfo(name="amount", type="NUMBER(10,2)"),
            ),
            expected_all_columns={
                "orders": (
                    ColumnInfo(name="id", type="NUMBER(38,0)"),
                    ColumnInfo(name="amount", type="NUMBER(10,2)"),
                )
            },
            expected_query_column_names=("ORDER_ID", "STATUS"),
        )
    ],
    ids=["discovers created table and view metadata"],
)
def test_given_relations_when_introspecting_then_returns_expected_metadata(
    test_case: SnowflakeSchemaIntrospectionTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    orders_relation: str = qualified_name(
        database=snowflake_database,
        schema=snowflake_schema,
        name="orders",
    )
    orders_view_relation: str = qualified_name(
        database=snowflake_database,
        schema=snowflake_schema,
        name="orders_view",
    )
    rewritten_statements: tuple[str, ...] = tuple(
        statement.replace("TABLE orders ", f"TABLE {orders_relation} ", 1)
        .replace("VIEW orders_view ", f"VIEW {orders_view_relation} ", 1)
        .replace("FROM orders", f"FROM {orders_relation}", 1)
        for statement in test_case.setup_sql
    )
    execute_statements(adapter=adapter, connection=connection, statements=rewritten_statements)

    relation_exists: bool = adapter.relation_exists(
        connection,
        database=snowflake_database,
        schema=snowflake_schema,
        name="orders",
    )
    schema_exists: bool = adapter.schema_exists(
        connection,
        database=snowflake_database,
        schema=snowflake_schema,
    )
    relation_names: tuple[str, ...] = tuple(
        relation.name
        for relation in adapter.list_relations(
            connection,
            database=snowflake_database,
            schemas=(snowflake_schema,),
        )
    )
    columns: tuple[ColumnInfo, ...] = adapter.get_columns(
        connection,
        database=snowflake_database,
        schema=snowflake_schema,
        name="orders",
    )
    all_columns: dict[str, tuple[ColumnInfo, ...]] = adapter.get_all_columns(
        connection,
        database=snowflake_database,
        schemas=(snowflake_schema,),
        names=("orders",),
    )
    query_column_names: tuple[str, ...] = adapter.query_column_names(
        connection,
        "SELECT * FROM (SELECT 1 AS order_id, 'ok' AS status) AS named_rows",
    )
    described_columns: tuple[ColumnInfo, ...] = adapter.describe_relation(
        connection, orders_relation
    )

    assert relation_exists == test_case.expected_relation_exists
    assert schema_exists == test_case.expected_schema_exists
    assert tuple(sorted(relation_names)) == tuple(sorted(test_case.expected_relation_names))
    assert columns == test_case.expected_columns
    assert all_columns == test_case.expected_all_columns
    assert query_column_names == test_case.expected_query_column_names
    assert described_columns == test_case.expected_columns


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeTableFreshnessMetadataTestCase(
            description="table freshness metadata advances after table DML",
            expected_value_kind="timestamp",
            expected_supports_metadata=True,
            expected_data_version_type=datetime,
        )
    ],
    ids=["table freshness metadata advances after table DML"],
)
def test_given_table_dml_when_getting_freshness_metadata_then_last_altered_advances(
    test_case: SnowflakeTableFreshnessMetadataTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    table_name: str = "freshness_orders"
    table_target: str = qualified_name(
        database=snowflake_database,
        schema=snowflake_schema,
        name=table_name,
    )
    execute_statements(
        adapter=adapter,
        connection=connection,
        statements=(
            f"CREATE OR REPLACE TABLE {table_target} (id NUMBER)",
            f"INSERT INTO {table_target} VALUES (1)",
        ),
    )
    initial_metadata: TableFreshnessMetadata = adapter.get_table_freshness_metadata(
        connection,
        database=snowflake_database,
        schema=snowflake_schema,
        name=table_name,
    )
    time.sleep(1)

    adapter.execute(connection, f"INSERT INTO {table_target} VALUES (2)")
    changed_metadata: TableFreshnessMetadata = adapter.get_table_freshness_metadata(
        connection,
        database=snowflake_database,
        schema=snowflake_schema,
        name=table_name,
    )
    batch_request: TableFreshnessRequest = TableFreshnessRequest(
        database=snowflake_database,
        schema=snowflake_schema,
        name=table_name,
    )
    batch_metadata: TableFreshnessMetadata = adapter.get_tables_freshness_metadata(
        connection,
        requests=(batch_request,),
    )[batch_request]

    assert adapter.supports_table_freshness_metadata() is test_case.expected_supports_metadata
    assert initial_metadata.value_kind == test_case.expected_value_kind
    assert changed_metadata.value_kind == test_case.expected_value_kind
    assert batch_metadata.value_kind == test_case.expected_value_kind
    assert isinstance(initial_metadata.data_version, test_case.expected_data_version_type)
    assert isinstance(changed_metadata.data_version, test_case.expected_data_version_type)
    assert isinstance(batch_metadata.data_version, test_case.expected_data_version_type)
    assert changed_metadata.data_version > initial_metadata.data_version
    initial_hash: str = source_freshness_record_from_observation(
        SourceFreshnessObservation(
            source_name="raw_orders",
            strategy=SourceFreshnessStrategy.ADAPTER,
            data_version=initial_metadata.data_version,
            value_kind=SourceFreshnessValueKind(initial_metadata.value_kind),
            observed_at=datetime.now(),
        ),
        virtual_environment_name="dev",
    ).data_version_hash
    repeated_initial_hash: str = source_freshness_record_from_observation(
        SourceFreshnessObservation(
            source_name="raw_orders",
            strategy=SourceFreshnessStrategy.ADAPTER,
            data_version=initial_metadata.data_version,
            value_kind=SourceFreshnessValueKind(initial_metadata.value_kind),
            observed_at=datetime.now(),
        ),
        virtual_environment_name="dev",
    ).data_version_hash
    changed_hash: str = source_freshness_record_from_observation(
        SourceFreshnessObservation(
            source_name="raw_orders",
            strategy=SourceFreshnessStrategy.ADAPTER,
            data_version=changed_metadata.data_version,
            value_kind=SourceFreshnessValueKind(changed_metadata.value_kind),
            observed_at=datetime.now(),
        ),
        virtual_environment_name="dev",
    ).data_version_hash
    assert repeated_initial_hash == initial_hash
    assert changed_hash != initial_hash


@pytest.mark.parametrize(
    "test_case",
    SCHEMA_DIFF_TEST_CASES,
    ids=[case.description for case in SCHEMA_DIFF_TEST_CASES],
)
def test_given_relations_when_diffing_schema_then_returns_expected_result(
    test_case: SnowflakeSchemaDiffTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    left_name: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="left_t"
    )
    right_name: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="right_t"
    )
    execute_statements(
        adapter=adapter,
        connection=connection,
        statements=(
            test_case.left_sql.replace("left_t", left_name),
            test_case.right_sql.replace("right_t", right_name),
        ),
    )

    result: SchemaDiffResult = adapter.diff_schema(connection, left=left_name, right=right_name)

    assert result == test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    ROW_DIFF_TEST_CASES,
    ids=[case.description for case in ROW_DIFF_TEST_CASES],
)
def test_given_relations_when_diffing_rows_then_returns_expected_result(
    test_case: SnowflakeRowDiffTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    left_name: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="left_t"
    )
    right_name: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="right_t"
    )
    execute_statements(
        adapter=adapter,
        connection=connection,
        statements=(
            test_case.left_sql.replace("left_t", left_name),
            test_case.right_sql.replace("right_t", right_name),
        ),
    )

    result: RowDiffResult = adapter.diff_rows(
        connection,
        left=left_name,
        right=right_name,
        unique_key=test_case.unique_key,
    )

    assert result.left_count == test_case.expected_result.left_count
    assert result.right_count == test_case.expected_result.right_count
    assert result.joined_count == test_case.expected_result.joined_count
    assert result.equal_count == test_case.expected_result.equal_count
    assert result.unequal_count == test_case.expected_result.unequal_count
    assert result.left_only_count == test_case.expected_result.left_only_count
    assert result.right_only_count == test_case.expected_result.right_only_count


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRowDiffSampleTestCase(
            description="returns unequal row samples for changed values",
            left_sql=(
                "CREATE OR REPLACE TABLE left_t AS "
                "SELECT * FROM (SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2 AS id, 'b' AS val)"
            ),
            right_sql=(
                "CREATE OR REPLACE TABLE right_t AS "
                "SELECT * FROM (SELECT 1 AS id, 'x' AS val UNION ALL SELECT 2 AS id, 'b' AS val)"
            ),
            unique_key="id",
            side="left",
            expected_unequal_samples=(
                RowDiffSampleRow(
                    key_values=(("id", 1),),
                    changed_cells=(RowDiffSampleCell(name="val", left_value="a", right_value="x"),),
                ),
            ),
        )
    ],
    ids=["returns unequal row samples for changed values"],
)
def test_given_relations_when_sampling_unequal_rows_then_returns_expected_examples(
    test_case: SnowflakeRowDiffSampleTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    left_name: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="left_t"
    )
    right_name: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="right_t"
    )
    execute_statements(
        adapter=adapter,
        connection=connection,
        statements=(
            test_case.left_sql.replace("left_t", left_name),
            test_case.right_sql.replace("right_t", right_name),
        ),
    )

    unequal_samples: tuple[RowDiffSampleRow, ...] = adapter.sample_unequal_rows(
        connection,
        left=left_name,
        right=right_name,
        unique_key=test_case.unique_key,
        limit=5,
    )

    assert unequal_samples == test_case.expected_unequal_samples


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRowDiffSampleTestCase(
            description="returns side only key samples",
            left_sql=(
                "CREATE OR REPLACE TABLE left_t AS "
                "SELECT * FROM (SELECT 1 AS id, 'a' AS val UNION ALL SELECT 2 AS id, 'b' AS val)"
            ),
            right_sql=(
                "CREATE OR REPLACE TABLE right_t AS "
                "SELECT * FROM (SELECT 2 AS id, 'b' AS val UNION ALL SELECT 3 AS id, 'c' AS val)"
            ),
            unique_key="id",
            side="left",
            expected_side_only_samples=((("id", 1),),),
        )
    ],
    ids=["returns side only key samples"],
)
def test_given_relations_when_sampling_side_only_rows_then_returns_expected_examples(
    test_case: SnowflakeRowDiffSampleTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    left_name: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="left_t"
    )
    right_name: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="right_t"
    )
    execute_statements(
        adapter=adapter,
        connection=connection,
        statements=(
            test_case.left_sql.replace("left_t", left_name),
            test_case.right_sql.replace("right_t", right_name),
        ),
    )

    side_only_samples: tuple[tuple[tuple[str, object], ...], ...] = adapter.sample_side_only_rows(
        connection,
        left=left_name,
        right=right_name,
        unique_key=test_case.unique_key,
        side=test_case.side,
        limit=5,
    )

    assert side_only_samples == test_case.expected_side_only_samples


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeBuildFlowTestCase(
            description="loads seed csv and builds table from select sql",
            seed_csv="id,name\n1,alice\n2,bob\n",
            expected_rows=((1, "alice"), (2, "bob")),
            expected_statement_count=5,
        )
    ],
    ids=["loads seed csv and builds table from select sql"],
)
def test_given_seed_and_table_flow_when_materializing_then_returns_expected_rows(
    test_case: SnowflakeBuildFlowTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
    tmp_path: Path,
) -> None:
    seed_path: Path = write_seed_file(
        tmp_path=tmp_path, filename="seed.csv", contents=test_case.seed_csv
    )
    seed_target: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="seed_data"
    )
    table_target: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="built_table"
    )
    recorder: StatementRecorder = build_statement_recorder()

    adapter.load_seed(
        connection,
        destination=seed_target,
        file_path=seed_path,
        columns=(ColumnInfo(name="id", type="INTEGER"), ColumnInfo(name="name", type="VARCHAR")),
        statement_recorder=recorder,
    )
    adapter.create_table_as(
        connection,
        destination=table_target,
        sql=f"SELECT id, name FROM {seed_target} ORDER BY id",
        statement_recorder=recorder,
    )

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, name FROM {table_target} ORDER BY id",
    )

    assert rows == test_case.expected_rows
    assert len(recorder.snapshot()) == test_case.expected_statement_count


RELATION_REUSE_COPY_TEST_CASES: tuple[SnowflakeRelationReuseCopyTestCase, ...] = (
    SnowflakeRelationReuseCopyTestCase(
        description="cheap reuse clones relation",
        hard_copy=False,
        destination_name="orders_cheap_reuse",
        expected_rows=((1, "alice"), (2, "bob")),
        expected_recorded_fragment=" CLONE ",
    ),
    SnowflakeRelationReuseCopyTestCase(
        description="hard copy reuse uses CTAS",
        hard_copy=True,
        destination_name="orders_hard_reuse",
        expected_rows=((1, "alice"), (2, "bob")),
        expected_recorded_fragment=" AS SELECT * FROM ",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    RELATION_REUSE_COPY_TEST_CASES,
    ids=[case.description for case in RELATION_REUSE_COPY_TEST_CASES],
)
def test_given_reuse_origin_when_creating_relation_then_snowflake_uses_expected_copy_mode(
    test_case: SnowflakeRelationReuseCopyTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    origin: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="orders_reuse_origin"
    )
    destination: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name=test_case.destination_name
    )
    recorder: StatementRecorder = build_statement_recorder()
    adapter.execute(
        connection,
        f"CREATE OR REPLACE TABLE {origin} AS "
        "SELECT 1 AS id, 'alice' AS name UNION ALL SELECT 2, 'bob'",
    )

    create_relation_from_reuse_origin(
        adapter=adapter,
        connection=connection,
        origin_relation=origin,
        destination_relation=destination,
        hard_copy=test_case.hard_copy,
        statement_recorder=recorder,
    )

    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, name FROM {destination} ORDER BY id",
    )
    recorded_sql: str = "\n".join(event.content for event in recorder.snapshot())

    assert rows == test_case.expected_rows
    assert test_case.expected_recorded_fragment in recorded_sql


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeMergeTestCase(
            description="merges source rows into target table",
            target_setup_sql=(
                "CREATE OR REPLACE TABLE merge_target (id NUMBER, val VARCHAR)",
                "INSERT INTO merge_target VALUES (1, 'old'), (2, 'keep')",
            ),
            source_sql=(
                "SELECT * FROM ("
                "SELECT 1 AS id, 'new' AS val UNION ALL "
                "SELECT 3 AS id, 'add' AS val"
                ")"
            ),
            unique_key="id",
            expected_rows=((1, "new"), (2, "keep"), (3, "add")),
        )
    ],
    ids=["merges source rows into target table"],
)
def test_given_merge_source_when_merging_then_target_matches_expected_rows(
    test_case: SnowflakeMergeTestCase,
    adapter: SnowflakeAdapter,
    connection: Any,
    snowflake_database: str,
    snowflake_schema: str,
) -> None:
    target_name: str = qualified_name(
        database=snowflake_database, schema=snowflake_schema, name="merge_target"
    )
    setup_sql: tuple[str, ...] = tuple(
        statement.replace("merge_target", target_name) for statement in test_case.target_setup_sql
    )
    execute_statements(adapter=adapter, connection=connection, statements=setup_sql)

    adapter.merge(
        connection,
        destination=target_name,
        sql=test_case.source_sql,
        unique_key=test_case.unique_key,
        statement_recorder=build_statement_recorder(),
    )
    rows: tuple[tuple[object, ...], ...] = fetch_rows(
        adapter=adapter,
        connection=connection,
        sql=f"SELECT id, val FROM {target_name} ORDER BY id",
    )

    assert rows == test_case.expected_rows
