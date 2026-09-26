"""Warehouse SQL text limits and their measurement units."""

from __future__ import annotations

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.executor.testing.main._sql_length import validate_unit_test_sql_length
from tests.unit.src.sqlbuild.adapter.contract.classes.base_adapter._test_types import (
    StatementSizeLimitTestCase,
)
from tests.unit.src.sqlbuild.adapter.contract.classes.base_adapter.helpers import (
    RecordingBaseAdapter,
)


@pytest.mark.parametrize(
    "test_case",
    (
        StatementSizeLimitTestCase("bigquery", BigQueryAdapter, (1_048_576, "bytes")),
        StatementSizeLimitTestCase("databricks", DatabricksAdapter, (16_777_216, "bytes")),
        StatementSizeLimitTestCase("base", RecordingBaseAdapter, None),
        StatementSizeLimitTestCase("duckdb", DuckDbAdapter, None),
        StatementSizeLimitTestCase("motherduck", MotherDuckAdapter, None),
        StatementSizeLimitTestCase("postgres", PostgresAdapter, None),
        StatementSizeLimitTestCase("snowflake", SnowflakeAdapter, None),
        StatementSizeLimitTestCase("sqlserver", SqlServerAdapter, None),
    ),
    ids=lambda case: case.description,
)
def test_given_adapter_when_reading_statement_limit_then_returns_documented_value_and_unit(
    test_case: StatementSizeLimitTestCase,
) -> None:
    assert test_case.adapter_factory().max_statement_size() == test_case.expected_limit


@pytest.mark.parametrize(
    "test_case",
    (
        StatementSizeLimitTestCase("bigquery", BigQueryAdapter, (1_048_576, "bytes")),
        StatementSizeLimitTestCase("databricks", DatabricksAdapter, (16_777_216, "bytes")),
    ),
    ids=lambda case: case.description,
)
def test_given_multibyte_sql_at_byte_limit_when_validating_then_accepts_exact_boundary(
    test_case: StatementSizeLimitTestCase,
) -> None:
    assert test_case.expected_limit is not None
    limit, _ = test_case.expected_limit
    sql: str = "é" * (limit // 2)
    validate_unit_test_sql_length(
        sql=sql, adapter=test_case.adapter_factory(), test_name="orders", model_name="orders"
    )


@pytest.mark.parametrize(
    "test_case",
    (
        StatementSizeLimitTestCase("bigquery", BigQueryAdapter, (1_048_576, "bytes")),
        StatementSizeLimitTestCase("databricks", DatabricksAdapter, (16_777_216, "bytes")),
    ),
    ids=lambda case: case.description,
)
def test_given_multibyte_sql_over_byte_limit_when_validating_then_reports_actual_bytes(
    test_case: StatementSizeLimitTestCase,
) -> None:
    assert test_case.expected_limit is not None
    limit, _ = test_case.expected_limit
    sql: str = "é" * (limit // 2) + "x"
    assert len(sql) < limit
    with pytest.raises(
        CompileInputError, match=f"is {limit + 1} bytes, which exceeds the maximum of {limit} bytes"
    ):
        validate_unit_test_sql_length(
            sql=sql, adapter=test_case.adapter_factory(), test_name="orders", model_name="orders"
        )


@pytest.mark.parametrize(
    "test_case",
    (
        StatementSizeLimitTestCase("base", RecordingBaseAdapter, None),
        StatementSizeLimitTestCase("duckdb", DuckDbAdapter, None),
        StatementSizeLimitTestCase("motherduck", MotherDuckAdapter, None),
        StatementSizeLimitTestCase("postgres", PostgresAdapter, None),
        StatementSizeLimitTestCase("snowflake", SnowflakeAdapter, None),
        StatementSizeLimitTestCase("sqlserver", SqlServerAdapter, None),
    ),
    ids=lambda case: case.description,
)
def test_given_sql_over_old_limit_when_no_static_limit_then_does_not_reject(
    test_case: StatementSizeLimitTestCase,
) -> None:
    assert test_case.adapter_factory().max_statement_size() == test_case.expected_limit
    validate_unit_test_sql_length(
        sql="é" * 1_100_000,
        adapter=test_case.adapter_factory(),
        test_name="orders",
        model_name="orders",
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
