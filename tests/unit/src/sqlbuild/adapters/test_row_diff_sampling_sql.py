import pytest

from sqlbuild.adapter.contract.models import RowDiffSampling
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import RowDiffSampleSqlTestCase

_GENERIC_HASH_FRAGMENTS: tuple[str, ...] = (
    "MD5(CONCAT_WS('|', '7'",
    "LENGTH(CAST(__key_union.order_id AS VARCHAR))",
    "__key_union.order_id, __key_union.line_id LIMIT 25",
)


@pytest.mark.parametrize(
    "test_case",
    [
        RowDiffSampleSqlTestCase(
            description="duckdb renders canonical deterministic sample",
            adapter=DuckDbAdapter(),
            expected_fragments=_GENERIC_HASH_FRAGMENTS,
        ),
        RowDiffSampleSqlTestCase(
            description="motherduck renders canonical deterministic sample",
            adapter=MotherDuckAdapter(),
            expected_fragments=_GENERIC_HASH_FRAGMENTS,
        ),
        RowDiffSampleSqlTestCase(
            description="postgres renders canonical deterministic sample",
            adapter=PostgresAdapter(),
            expected_fragments=_GENERIC_HASH_FRAGMENTS,
        ),
        RowDiffSampleSqlTestCase(
            description="snowflake renders canonical deterministic sample",
            adapter=SnowflakeAdapter(),
            expected_fragments=_GENERIC_HASH_FRAGMENTS,
        ),
        RowDiffSampleSqlTestCase(
            description="databricks renders canonical deterministic sample",
            adapter=DatabricksAdapter(),
            expected_fragments=_GENERIC_HASH_FRAGMENTS,
        ),
        RowDiffSampleSqlTestCase(
            description="bigquery renders canonical deterministic sample",
            adapter=BigQueryAdapter(),
            expected_fragments=(
                "TO_HEX(MD5(CONCAT('7', '|'",
                "LENGTH(CAST(__key_union.order_id AS STRING))",
                "__key_union.order_id, __key_union.line_id LIMIT 25",
            ),
        ),
        RowDiffSampleSqlTestCase(
            description="sqlserver renders canonical deterministic sample",
            adapter=SqlServerAdapter(),
            expected_fragments=(
                "SELECT TOP (25) order_id, line_id",
                "HASHBYTES('SHA2_256'",
                "DATALENGTH(CAST(__key_union.line_id AS NVARCHAR(MAX)))",
                "__key_union.order_id, __key_union.line_id",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_composite_keys_when_rendering_sample_then_adapter_hashes_and_tie_breaks(
    test_case: RowDiffSampleSqlTestCase,
) -> None:
    sql: str = test_case.adapter._render_row_diff_sample_keys_sql(
        key_union_sql="SELECT order_id, line_id FROM bounded_keys",
        keys=("order_id", "line_id"),
        sampling=RowDiffSampling(row_limit=25, seed=7),
    )

    assert all(fragment in sql for fragment in test_case.expected_fragments)
