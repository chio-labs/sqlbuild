from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import QueryResult
from sqlbuild.adapter.shared.types import CursorKind
from sqlbuild.integrations.bigquery.client import BigQueryAdapter, _BigQueryConnection
from tests.unit.src.sqlbuild.integrations.bigquery._test_types import (
    BigQueryConnectErrorTestCase,
    BigQueryQueryTestCase,
    BigQueryRenderCursorBoundLiteralTestCase,
    BigQueryRenderQualifiedNameTestCase,
    BigQueryRenderSchemaTestCase,
    BigQuerySchemaExistsTestCase,
)
from tests.unit.src.sqlbuild.integrations.bigquery.helpers import (
    FakeBigQueryClient,
    FakeBigQueryRows,
)

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
    BIGQUERY_RENDER_CURSOR_BOUND_LITERAL_TEST_CASES,
    ids=[case.description for case in BIGQUERY_RENDER_CURSOR_BOUND_LITERAL_TEST_CASES],
)
def test_given_cursor_bounds_when_rendering_then_bigquery_returns_expected_literal(
    test_case: BigQueryRenderCursorBoundLiteralTestCase,
) -> None:
    adapter: BigQueryAdapter = BigQueryAdapter()

    result: str = adapter.render_cursor_bound_literal(test_case.value, test_case.cursor_type)

    assert result == test_case.expected_literal
