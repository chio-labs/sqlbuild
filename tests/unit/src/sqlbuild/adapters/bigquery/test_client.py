from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.adapter.shared.exceptions import AdapterUserError
from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    CursorValue,
    ExpressionInferenceProfile,
    QueryResult,
    RowDiffColumnResult,
    RowDiffResult,
    RowDiffSampleCell,
    RowDiffSampleRow,
    SchemaDiffResult,
    TableFreshnessMetadata,
    TableFreshnessRequest,
)
from sqlbuild.adapter.shared.types import CursorKind, FunctionNullabilityRule
from sqlbuild.adapters.bigquery.client import BigQueryAdapter, _BigQueryConnection
from sqlbuild.compiler.compile.models.core import (
    FunctionArgument,
    FunctionReturnColumn,
)
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.lineage.types import InferredNullability
from tests.unit.src.sqlbuild.adapters.bigquery._test_types import (
    BigQueryConnectErrorTestCase,
    BigQueryCountRowsTestCase,
    BigQueryExecutionErrorTestCase,
    BigQueryExpressionInferenceProfileTestCase,
    BigQueryPruneSqlTestCase,
    BigQueryQueryTestCase,
    BigQueryRenderCloneTestCase,
    BigQueryRenderCursorBoundLiteralTestCase,
    BigQueryRenderDeleteInsertTestCase,
    BigQueryRenderDropViewTestCase,
    BigQueryRenderPythonFunctionTestCase,
    BigQueryRenderQualifiedNameTestCase,
    BigQueryRenderSchemaTestCase,
    BigQueryRenderTableFunctionTestCase,
    BigQueryRowDiffTestCase,
    BigQuerySampleRowsTestCase,
    BigQuerySchemaDiffTestCase,
    BigQuerySchemaExistsTestCase,
    BigQueryTableFreshnessBatchTestCase,
    BigQueryTableFreshnessWildcardTestCase,
)
from tests.unit.src.sqlbuild.adapters.bigquery.helpers import (
    FakeBigQueryBadRequest,
    FakeBigQueryClient,
    FakeBigQueryRows,
    build_count_rows_execute,
    build_row_diff_execute,
    build_sample_rows_execute,
    fake_row_diff_describe_relation,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryExpressionInferenceProfileTestCase(
            description="returns BigQuery inference rules",
            expected_sql_analysis_dialect="bigquery",
            expected_identifier_limit=1024,
            expected_rule_results={
                "IF": InferredNullability.NON_NULL,
                "LOWER": InferredNullability.NON_NULL,
            },
        )
    ],
    ids=["returns BigQuery inference rules"],
)
def test_given_bigquery_adapter_when_getting_inference_profile_then_returns_expected_rules(
    test_case: BigQueryExpressionInferenceProfileTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    profile: ExpressionInferenceProfile = adapter.expression_inference_profile()

    assert profile.sql_analysis_dialect == test_case.expected_sql_analysis_dialect
    assert adapter.maximum_identifier_length() == test_case.expected_identifier_limit
    if_rule: FunctionNullabilityRule | None = profile.function_nullability_rule("IF")
    lower_rule: FunctionNullabilityRule | None = profile.function_nullability_rule("LOWER")
    assert if_rule is not None
    assert lower_rule is not None
    assert (
        if_rule(
            (
                InferredNullability.UNKNOWN,
                InferredNullability.NON_NULL,
                InferredNullability.NON_NULL,
            )
        )
        == test_case.expected_rule_results["IF"]
    )
    assert lower_rule((InferredNullability.NON_NULL,)) == test_case.expected_rule_results["LOWER"]


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryPruneSqlTestCase(
            description="renders fingerprint pruning with correlated exists",
            database="example-project",
            schema="analytics",
            retain_versions=5,
            expected_fragments=(
                "DELETE FROM `example-project.analytics._sqlbuild_fingerprints` "
                "AS target WHERE EXISTS",
                "ROW_NUMBER() OVER",
                "PARTITION BY node_type, node_name",
                "ORDER BY ts DESC, run_id DESC",
                "__sqlbuild_history_rank > 5",
                "target.node_type = stale.node_type",
                "target.node_name = stale.node_name",
            ),
        )
    ],
    ids=["renders fingerprint pruning with correlated exists"],
)
def test_given_fingerprint_table_when_rendering_prune_then_bigquery_uses_history_rank(
    test_case: BigQueryPruneSqlTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

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
        BigQueryPruneSqlTestCase(
            description="renders source freshness pruning with null-safe full identity",
            database="example-project",
            schema="analytics",
            retain_versions=3,
            expected_fragments=(
                "DELETE FROM `example-project.analytics._sqlbuild_source_freshness` "
                "AS target WHERE EXISTS",
                "ROW_NUMBER() OVER",
                "PARTITION BY source_name, target_database, target_schema, target_name",
                "ORDER BY observed_at DESC, run_id DESC",
                "__sqlbuild_history_rank > 3",
                "target.target_database IS NOT DISTINCT FROM stale.target_database",
            ),
        )
    ],
    ids=["renders source freshness pruning with null-safe full identity"],
)
def test_given_source_freshness_table_when_rendering_prune_then_bigquery_uses_history_rank(
    test_case: BigQueryPruneSqlTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

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
        BigQueryTableFreshnessBatchTestCase(
            description="uses table storage metadata for multiple tables",
            location="US",
            expected_data_versions=(
                datetime(2026, 1, 2, 3, 4, 5),
                datetime(2026, 1, 3, 4, 5, 6),
            ),
            expected_query_fragments=(
                "FROM `example-project.region-us`.INFORMATION_SCHEMA.TABLE_STORAGE",
                "storage_last_modified_time",
                "ORDERS",
                "CUSTOMERS",
            ),
        )
    ],
    ids=["uses table storage metadata for multiple tables"],
)
def test_given_physical_tables_when_getting_freshness_metadata_then_bigquery_uses_table_storage(
    test_case: BigQueryTableFreshnessBatchTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()
    requests: tuple[TableFreshnessRequest, ...] = (
        TableFreshnessRequest(database="example-project", schema="raw", name="ORDERS"),
        TableFreshnessRequest(database="example-project", schema="raw", name="CUSTOMERS"),
    )
    client: FakeBigQueryClient = FakeBigQueryClient(
        rows=FakeBigQueryRows(
            columns=("table_schema", "table_name", "storage_last_modified_time"),
            rows=(
                ("raw", "ORDERS", test_case.expected_data_versions[0]),
                ("raw", "CUSTOMERS", test_case.expected_data_versions[1]),
            ),
        )
    )
    connection: _BigQueryConnection = _BigQueryConnection(
        client=client,
        location=test_case.location,
    )

    metadata_by_request: dict[TableFreshnessRequest, TableFreshnessMetadata] = (
        adapter.get_tables_freshness_metadata(connection, requests=requests)
    )

    assert (
        tuple(metadata_by_request[request].data_version for request in requests)
        == test_case.expected_data_versions
    )
    assert all(metadata.value_kind == "timestamp" for metadata in metadata_by_request.values())
    assert len(client.queries) == 1
    sql, location = client.queries[0]
    assert location == test_case.location
    for fragment in test_case.expected_query_fragments:
        assert fragment in sql


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryTableFreshnessWildcardTestCase(
            description="rejects wildcard table metadata freshness",
            table_name="events_*",
            expected_error_fragment="does not support wildcard tables",
        )
    ],
    ids=["rejects wildcard table metadata freshness"],
)
def test_given_wildcard_table_when_getting_freshness_metadata_then_bigquery_raises_clear_error(
    test_case: BigQueryTableFreshnessWildcardTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()
    request: TableFreshnessRequest = TableFreshnessRequest(
        database="example-project",
        schema="raw",
        name=test_case.table_name,
    )
    connection: _BigQueryConnection = _BigQueryConnection(
        client=FakeBigQueryClient(),
        location="US",
    )

    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        adapter.get_tables_freshness_metadata(connection, requests=(request,))


BIGQUERY_QUERY_TEST_CASES: list[BigQueryQueryTestCase] = [
    BigQueryQueryTestCase(
        description="returns limited rows and truncation flag",
        sql="SELECT id, name FROM demo",
        limit=2,
        expected_columns=("id", "name"),
        expected_rows=((1, "a"), (2, "b")),
        expected_truncated=True,
    ),
    BigQueryQueryTestCase(
        description="returns all rows when limit is none",
        sql="SELECT id, name FROM demo",
        limit=None,
        expected_columns=("id", "name"),
        expected_rows=((1, "a"), (2, "b"), (3, "c")),
        expected_truncated=False,
    ),
]

BIGQUERY_RENDER_SCHEMA_TEST_CASES: list[BigQueryRenderSchemaTestCase] = [
    BigQueryRenderSchemaTestCase(
        description="includes configured location in create schema",
        database="example-project",
        schema="dev",
        location="europe-west2",
        expected_sql=(
            "CREATE SCHEMA IF NOT EXISTS `example-project.dev` OPTIONS(location = 'europe-west2')"
        ),
    ),
    BigQueryRenderSchemaTestCase(
        description="omits location when none configured",
        database="example-project",
        schema="dev",
        location=None,
        expected_sql="CREATE SCHEMA IF NOT EXISTS `example-project.dev`",
    ),
]

BIGQUERY_RENDER_QUALIFIED_NAME_TEST_CASES: list[BigQueryRenderQualifiedNameTestCase] = [
    BigQueryRenderQualifiedNameTestCase(
        description="quotes three-part BigQuery relation path",
        database="example-project",
        schema="dev",
        name="stg_customers",
        expected_qualified_name="`example-project.dev.stg_customers`",
    ),
    BigQueryRenderQualifiedNameTestCase(
        description="quotes two-part BigQuery relation path",
        database=None,
        schema="dev",
        name="stg_customers",
        expected_qualified_name="`dev.stg_customers`",
    ),
]

BIGQUERY_RENDER_CLONE_TEST_CASES: list[BigQueryRenderCloneTestCase] = [
    BigQueryRenderCloneTestCase(
        description="renders zero copy table clone by default",
        source="example-project.prod.fact_orders",
        target="example-project.dev.fact_orders",
        hard_copy=False,
        expected_statements=(
            "CREATE TABLE `example-project.dev.fact_orders` "
            "CLONE `example-project.prod.fact_orders`",
        ),
        expected_supports_zero_copy=True,
    ),
    BigQueryRenderCloneTestCase(
        description="renders CTAS when hard copy is requested",
        source="`example-project.prod.fact_orders`",
        target="`example-project.dev.fact_orders`",
        hard_copy=True,
        expected_statements=(
            "CREATE OR REPLACE TABLE `example-project.dev.fact_orders` AS "
            "SELECT * FROM `example-project.prod.fact_orders`",
        ),
        expected_supports_zero_copy=True,
    ),
]

BIGQUERY_SCHEMA_EXISTS_TEST_CASES: list[BigQuerySchemaExistsTestCase] = [
    BigQuerySchemaExistsTestCase(
        description="returns true when dataset exists",
        missing_dataset=False,
        expected_exists=True,
    ),
    BigQuerySchemaExistsTestCase(
        description="returns false when dataset is missing",
        missing_dataset=True,
        expected_exists=False,
    ),
]

BIGQUERY_CONNECT_ERROR_TEST_CASES: list[BigQueryConnectErrorTestCase] = [
    BigQueryConnectErrorTestCase(
        description="requires explicit connection project",
        config={"location": "europe-west2"},
        expected_error_fragment="BigQuery connection requires non-empty 'project'",
    ),
    BigQueryConnectErrorTestCase(
        description="rejects blank connection project",
        config={"project": " ", "location": "europe-west2"},
        expected_error_fragment="BigQuery connection requires non-empty 'project'",
    ),
]

BIGQUERY_RENDER_CURSOR_BOUND_LITERAL_TEST_CASES: list[BigQueryRenderCursorBoundLiteralTestCase] = [
    BigQueryRenderCursorBoundLiteralTestCase(
        description="renders timestamp cursor bounds as typed literals",
        value="2024-01-15T00:00:00",
        cursor_type=CursorKind.TIMESTAMP,
        expected_literal="TIMESTAMP '2024-01-15T00:00:00'",
    ),
    BigQueryRenderCursorBoundLiteralTestCase(
        description="renders integer cursor bounds without quotes",
        value="42",
        cursor_type=CursorKind.INTEGER,
        expected_literal="42",
    ),
]

BIGQUERY_SCHEMA_DIFF_TEST_CASES: list[BigQuerySchemaDiffTestCase] = [
    BigQuerySchemaDiffTestCase(
        description="detects added removed and changed column types",
        expected_result=SchemaDiffResult(
            added_columns=(ColumnInfo(name="new_col", type="DATE"),),
            removed_columns=(ColumnInfo(name="status", type="STRING"),),
            type_changed_columns=(
                (ColumnInfo(name="id", type="INT64"), ColumnInfo(name="id", type="STRING")),
            ),
        ),
        left_relation_columns=(
            ColumnInfo(name="id", type="INT64"),
            ColumnInfo(name="status", type="STRING"),
        ),
        right_relation_columns=(
            ColumnInfo(name="id", type="STRING"),
            ColumnInfo(name="new_col", type="DATE"),
        ),
    ),
    BigQuerySchemaDiffTestCase(
        description="ignores semantically equivalent type aliases",
        expected_result=SchemaDiffResult(),
        left_relation_columns=(ColumnInfo(name="id", type="INT64"),),
        right_relation_columns=(ColumnInfo(name="id", type="INTEGER"),),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_QUERY_TEST_CASES,
    ids=[case.description for case in BIGQUERY_QUERY_TEST_CASES],
)
def test_given_bigquery_rows_when_querying_then_returns_normalized_result(
    test_case: BigQueryQueryTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()
    connection: _BigQueryConnection = _BigQueryConnection(
        client=FakeBigQueryClient(
            rows=FakeBigQueryRows(
                columns=test_case.expected_columns,
                rows=((1, "a"), (2, "b"), (3, "c")),
            )
        ),
        location="europe-west2",
    )

    result: QueryResult = adapter.query(connection, test_case.sql, limit=test_case.limit)

    assert result.columns == test_case.expected_columns
    assert result.rows == test_case.expected_rows
    assert result.truncated is test_case.expected_truncated
    assert connection.client.queries == [(test_case.sql, "europe-west2")]


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_RENDER_SCHEMA_TEST_CASES,
    ids=[case.description for case in BIGQUERY_RENDER_SCHEMA_TEST_CASES],
)
def test_given_bigquery_schema_target_when_rendering_then_returns_create_schema_sql(
    test_case: BigQueryRenderSchemaTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()
    adapter._location = test_case.location

    statements: tuple[str, ...] = adapter.render_create_schema(
        database=test_case.database,
        schema=test_case.schema,
    )

    assert statements == (test_case.expected_sql,)


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_RENDER_QUALIFIED_NAME_TEST_CASES,
    ids=[case.description for case in BIGQUERY_RENDER_QUALIFIED_NAME_TEST_CASES],
)
def test_given_bigquery_relation_parts_when_rendering_then_quotes_qualified_name(
    test_case: BigQueryRenderQualifiedNameTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    qualified_name: str | None = adapter.render_qualified_name(
        database=test_case.database,
        schema=test_case.schema,
        name=test_case.name,
    )

    assert qualified_name == test_case.expected_qualified_name


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryRenderPythonFunctionTestCase(
            description="renders Python UDF DDL with runtime entry point and packages",
            expected_sql=(
                "CREATE OR REPLACE FUNCTION `demo.udfs.is_positive_int`(a_string STRING)\n"
                "RETURNS INT64\n"
                "LANGUAGE python\n"
                "OPTIONS(\n"
                '  runtime_version = "python-3.11",\n'
                '  entry_point = "main",\n'
                "  packages = ['numpy', 'pandas==1.5.0']\n"
                ")\n"
                "AS r'''\n"
                "def main(a_string):\n"
                "    return 1 if a_string else 0\n"
                "'''"
            ),
        )
    ],
    ids=["renders Python UDF DDL with runtime entry point and packages"],
)
def test_given_python_function_when_rendering_then_bigquery_returns_expected_ddl(
    test_case: BigQueryRenderPythonFunctionTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        destination="demo.udfs.is_positive_int",
        arguments=(FunctionArgument(name="a_string", type="STRING"),),
        returns="INT64",
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
        BigQueryRenderTableFunctionTestCase(
            description="renders table function DDL with inferred BigQuery return schema",
            expected_sql=(
                "CREATE OR REPLACE TABLE FUNCTION `demo.analytics.customer_orders`"
                "(p_customer_id INT64)\n"
                "AS (\nSELECT order_id FROM `demo.analytics.fact_orders`\n"
                "WHERE customer_id = p_customer_id\n)"
            ),
        )
    ],
    ids=["renders table function DDL with inferred BigQuery return schema"],
)
def test_given_table_function_when_rendering_then_bigquery_returns_expected_ddl(
    test_case: BigQueryRenderTableFunctionTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    statements: tuple[str, ...] = adapter.render_create_function(
        destination="demo.analytics.customer_orders",
        arguments=(FunctionArgument(name="p_customer_id", type="INT64"),),
        returns="TABLE",
        body_sql=(
            "SELECT order_id FROM `demo.analytics.fact_orders`\nWHERE customer_id = p_customer_id"
        ),
        return_columns=(FunctionReturnColumn(name="order_id", type="INT64"),),
    )

    assert statements == (test_case.expected_sql,)


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryRenderTableFunctionTestCase(
            description="quotes fully qualified function calls with hyphenated project ids",
            expected_sql=(
                "`project-d5f92072.europe_west2.customer_orders`(1)|"
                "`project-d5f92072.europe_west2.is_completed_order`(status)"
            ),
        )
    ],
    ids=["quotes fully qualified function calls with hyphenated project ids"],
)
def test_given_bigquery_function_call_when_rendering_then_quotes_qualified_target(
    test_case: BigQueryRenderTableFunctionTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    rendered_call: str = "|".join(
        (
            adapter.render_table_function_call(
                target="project-d5f92072.europe_west2.customer_orders",
                call_suffix_sql="(1)",
            ),
            adapter.render_udf_call(
                target="project-d5f92072.europe_west2.is_completed_order",
                call_suffix_sql="(status)",
            ),
        )
    )

    assert rendered_call == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_SCHEMA_EXISTS_TEST_CASES,
    ids=[case.description for case in BIGQUERY_SCHEMA_EXISTS_TEST_CASES],
)
def test_given_bigquery_dataset_state_when_checking_schema_exists_then_returns_expected(
    test_case: BigQuerySchemaExistsTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()
    client: FakeBigQueryClient = FakeBigQueryClient(missing_dataset=test_case.missing_dataset)
    connection: _BigQueryConnection = _BigQueryConnection(client=client, location="europe-west2")

    exists: bool = adapter.schema_exists(
        connection,
        database="example-project",
        schema="dev",
    )

    assert exists is test_case.expected_exists
    assert client.dataset_ids == ["example-project.dev"]


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_CONNECT_ERROR_TEST_CASES,
    ids=[case.description for case in BIGQUERY_CONNECT_ERROR_TEST_CASES],
)
def test_given_missing_bigquery_project_when_connecting_then_raises_clear_error(
    test_case: BigQueryConnectErrorTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        adapter.connect(test_case.config)


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryExecutionErrorTestCase(
            description="includes BigQuery error details from failed jobs",
            error_message="400 GET https://bigquery.googleapis.com/bigquery/v2/projects/demo",
            error_details=[{"message": "Unrecognized name: missing_column at [1:8]"}],
            expected_error_fragment="missing_column",
            expected_error_code="A104",
        ),
    ],
    ids=["includes BigQuery error details from failed jobs"],
)
def test_given_bigquery_job_failure_when_executing_then_includes_error_details(
    test_case: BigQueryExecutionErrorTestCase,
) -> None:
    connection: _BigQueryConnection = _BigQueryConnection(
        client=FakeBigQueryClient(
            query_error=FakeBigQueryBadRequest(
                test_case.error_message,
                errors=test_case.error_details,
            )
        ),
        location="europe-west2",
    )
    adapter: BigQueryAdapter = BigQueryAdapter()

    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment) as error:
        adapter.execute(connection, "SELECT missing_column")

    assert error.value.code == test_case.expected_error_code


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_RENDER_CURSOR_BOUND_LITERAL_TEST_CASES,
    ids=[case.description for case in BIGQUERY_RENDER_CURSOR_BOUND_LITERAL_TEST_CASES],
)
def test_given_cursor_bounds_when_rendering_then_bigquery_returns_expected_literal(
    test_case: BigQueryRenderCursorBoundLiteralTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    result: str = adapter.render_cursor_bound_literal(test_case.value, test_case.cursor_type)

    assert result == test_case.expected_literal


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_RENDER_CLONE_TEST_CASES,
    ids=[case.description for case in BIGQUERY_RENDER_CLONE_TEST_CASES],
)
def test_given_clone_request_when_rendering_then_bigquery_uses_expected_clone_sql(
    test_case: BigQueryRenderCloneTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    statements: tuple[str, ...] = adapter.render_clone(
        origin=test_case.source,
        destination=test_case.target,
        hard_copy=test_case.hard_copy,
    )

    assert adapter.supports_zero_copy_clone() is test_case.expected_supports_zero_copy
    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryRenderDropViewTestCase(
            description="quotes hyphenated project id when dropping view",
            target="test-project.dataset.__sqb_123456789abc__model__stg_events",
            expected_statements=(
                "DROP VIEW IF EXISTS `test-project.dataset.__sqb_123456789abc__model__stg_events`",
            ),
        )
    ],
    ids=["quotes hyphenated project id when dropping view"],
)
def test_given_bigquery_adapter_when_rendering_drop_view_then_quotes_target(
    test_case: BigQueryRenderDropViewTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    result: tuple[str, ...] = adapter.render_drop_view(destination=test_case.target)

    assert result == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryRenderDeleteInsertTestCase(
            description="renders cursor delete insert as merge replace window",
            expected_fragments=(
                "MERGE `example-project.dev.events` AS __target",
                "USING (SELECT id, event_time FROM delta_events) AS __source ON FALSE",
                "WHEN NOT MATCHED BY TARGET THEN INSERT (`id`, `event_time`)",
                "WHEN NOT MATCHED BY SOURCE AND __target.`event_time` >= "
                "TIMESTAMP '2026-01-01T00:00:00'",
                "AND __target.`event_time` < TIMESTAMP '2026-01-02T00:00:00' THEN DELETE",
            ),
            unexpected_fragments=(
                "DELETE FROM",
                "INSERT INTO",
            ),
        ),
    ],
    ids=["renders cursor delete insert as merge replace window"],
)
def test_given_delete_insert_cursor_when_rendering_then_bigquery_uses_merge(
    test_case: BigQueryRenderDeleteInsertTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    statements: tuple[str, ...] = adapter.render_delete_insert_cursor(
        destination="example-project.dev.events",
        sql="SELECT id, event_time FROM delta_events",
        cursor_column="event_time",
        cursor_start="2026-01-01T00:00:00",
        cursor_end="2026-01-02T00:00:00",
        columns=("id", "event_time"),
    )
    rendered_sql: str = statements[0]

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in rendered_sql

    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in rendered_sql


@pytest.mark.parametrize(
    "test_case",
    BIGQUERY_SCHEMA_DIFF_TEST_CASES,
    ids=[case.description for case in BIGQUERY_SCHEMA_DIFF_TEST_CASES],
)
def test_given_bigquery_relations_when_diffing_schema_then_returns_expected_result(
    test_case: BigQuerySchemaDiffTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()
    monkeypatch.setattr(
        adapter,
        "describe_relation",
        lambda connection, relation: (
            test_case.left_relation_columns
            if relation == "left_relation"
            else test_case.right_relation_columns
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
        BigQueryRowDiffTestCase(
            description="returns row diff counts and column mismatch counts",
            expected_result=RowDiffResult(
                left_count=3,
                right_count=3,
                joined_count=4,
                equal_count=1,
                unequal_count=1,
                left_only_count=1,
                right_only_count=1,
                column_results=(
                    RowDiffColumnResult(name="val", mismatched_count=1, tolerance=None),
                ),
            ),
        )
    ],
    ids=["returns row diff counts and column mismatch counts"],
)
def test_given_bigquery_relations_when_diffing_rows_then_returns_expected_result(
    test_case: BigQueryRowDiffTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()
    executed_sql: list[str] = []

    monkeypatch.setattr(adapter, "describe_relation", fake_row_diff_describe_relation)
    monkeypatch.setattr(adapter, "execute", build_row_diff_execute(executed_sql))

    result: RowDiffResult = adapter.diff_rows(
        connection=object(),
        left="left_relation",
        right="right_relation",
        unique_key="id",
    )

    assert result == test_case.expected_result
    assert any("FULL OUTER JOIN" in sql for sql in executed_sql)


@pytest.mark.parametrize(
    "test_case",
    [
        BigQuerySampleRowsTestCase(
            description="returns unequal and side-only samples",
            expected_unequal_samples=(
                RowDiffSampleRow(
                    key_values=(("id", 1),),
                    changed_cells=(RowDiffSampleCell(name="val", left_value="a", right_value="x"),),
                ),
            ),
            expected_side_only_samples=((("id", 1),),),
        )
    ],
    ids=["returns unequal and side-only samples"],
)
def test_given_bigquery_relations_when_sampling_rows_then_returns_expected_examples(
    test_case: BigQuerySampleRowsTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    monkeypatch.setattr(adapter, "describe_relation", fake_row_diff_describe_relation)
    monkeypatch.setattr(adapter, "execute", build_sample_rows_execute())

    unequal_samples: tuple[RowDiffSampleRow, ...] = adapter.sample_unequal_rows(
        connection=object(),
        left="left_relation",
        right="right_relation",
        unique_key="id",
        limit=5,
    )
    side_only_samples: tuple[tuple[tuple[str, object], ...], ...] = adapter.sample_side_only_rows(
        connection=object(),
        left="left_relation",
        right="right_relation",
        unique_key="id",
        side="left",
        limit=5,
    )

    assert unequal_samples == test_case.expected_unequal_samples
    assert side_only_samples == test_case.expected_side_only_samples


@pytest.mark.parametrize(
    "test_case",
    [
        BigQueryCountRowsTestCase(
            description="uses typed timestamp cursor filter",
            expected_count=2,
            expected_sql=(
                "SELECT COUNT(*) FROM left_relation WHERE updated_at >= "
                "TIMESTAMP '2026-04-01 00:00:00' AND updated_at < "
                "TIMESTAMP '2026-04-02 00:00:00'"
            ),
        )
    ],
    ids=["uses typed timestamp cursor filter"],
)
def test_given_timestamp_cursor_when_counting_rows_then_bigquery_uses_typed_filter(
    test_case: BigQueryCountRowsTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()
    executed_sql: list[str] = []

    monkeypatch.setattr(adapter, "execute", build_count_rows_execute(executed_sql))

    result: int = adapter.count_rows(
        connection=object(),
        relation="left_relation",
        cursor_column="updated_at",
        start_cursor=CursorValue(kind=CursorKind.TIMESTAMP, value=datetime(2026, 4, 1, 0, 0, 0)),
        end_cursor=CursorValue(kind=CursorKind.TIMESTAMP, value=datetime(2026, 4, 2, 0, 0, 0)),
    )

    assert result == test_case.expected_count
    assert executed_sql == [test_case.expected_sql]
