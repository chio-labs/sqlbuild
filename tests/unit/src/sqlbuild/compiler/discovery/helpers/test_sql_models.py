from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.helpers.sql_models import parse_model_sql
from tests.unit.src.sqlbuild.compiler.discovery.helpers._test_types import (
    ParseModelSqlErrorTestCase,
    ParseModelSqlHeaderTestCase,
)

TEST_CASES: list[ParseModelSqlHeaderTestCase] = [
    ParseModelSqlHeaderTestCase(
        description="accepts an empty model header",
        contents="""
        MODEL ();

        SELECT 1 AS order_id
        """,
        expected_header_values={},
        expected_query="SELECT 1 AS order_id",
    ),
    ParseModelSqlHeaderTestCase(
        description="accepts mixed block and inline header mappings",
        contents="""
        MODEL (
          materialized: "incremental",
          unique_key: ["order_id"],
          config:
            cluster_by: ["event_day"]
            transient: true,
          schema_change_backfill: {add_column: "bounded(30d)", type_change: "full"},
        );

        SELECT order_id, event_day FROM raw_orders
        """,
        expected_header_values={
            "materialized": "incremental",
            "unique_key": ["order_id"],
            "config": {
                "cluster_by": ["event_day"],
                "transient": True,
            },
            "schema_change_backfill": {
                "add_column": "bounded(30d)",
                "type_change": "full",
            },
        },
        expected_query="SELECT order_id, event_day FROM raw_orders",
    ),
    ParseModelSqlHeaderTestCase(
        description="accepts blank lines and indentation inside the header",
        contents="""

        MODEL (
            materialized: "table",

            tags: ["core"],
            enabled: true,
        );

        SELECT 1
        """,
        expected_header_values={
            "materialized": "table",
            "tags": ["core"],
            "enabled": True,
        },
        expected_query="SELECT 1",
    ),
    ParseModelSqlHeaderTestCase(
        description="accepts quoted and unquoted plain string scalars",
        contents="""
        MODEL (
          materialized: table,
          schema: "analytics",
          database: preserve,
          query_change_backfill: bounded(30d),
        );

        SELECT 1
        """,
        expected_header_values={
            "materialized": "table",
            "schema": "analytics",
            "database": "preserve",
            "query_change_backfill": "bounded(30d)",
        },
        expected_query="SELECT 1",
    ),
    ParseModelSqlHeaderTestCase(
        description="accepts quoted, unquoted, and mixed string lists",
        contents="""
        MODEL (
          tags: [core, "finance", marts],
          unique_key: ["order_id", customer_id],
        );

        SELECT 1
        """,
        expected_header_values={
            "tags": ["core", "finance", "marts"],
            "unique_key": ["order_id", "customer_id"],
        },
        expected_query="SELECT 1",
    ),
    ParseModelSqlHeaderTestCase(
        description="accepts template-like strings when quoted",
        contents="""
        MODEL (
          schema: "dev_${user}",
          database: "ci_${ENV:GITHUB_RUN_ID}_${CTX:schema}",
          alias: "fact_orders",
        );

        SELECT 1
        """,
        expected_header_values={
            "schema": "dev_${user}",
            "database": "ci_${ENV:GITHUB_RUN_ID}_${CTX:schema}",
            "alias": "fact_orders",
        },
        expected_query="SELECT 1",
    ),
    ParseModelSqlHeaderTestCase(
        description="accepts nested inline mappings with mixed quoted and unquoted strings",
        contents="""
        MODEL (
          schema_change_backfill: {add_column: bounded(30d), type_change: "full"},
          config: {cluster_by: [event_day, "region"], transient: true},
        );

        SELECT 1
        """,
        expected_header_values={
            "schema_change_backfill": {
                "add_column": "bounded(30d)",
                "type_change": "full",
            },
            "config": {
                "cluster_by": ["event_day", "region"],
                "transient": True,
            },
        },
        expected_query="SELECT 1",
    ),
    ParseModelSqlHeaderTestCase(
        description="accepts booleans and integers from unquoted YAML scalars",
        contents="""
        MODEL (
          enabled: false,
          batch_concurrency: 4,
          config: {
            transient: true,
          },
        );

        SELECT 1
        """,
        expected_header_values={
            "enabled": False,
            "batch_concurrency": 4,
            "config": {
                "transient": True,
            },
        },
        expected_query="SELECT 1",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_sql_model_header_variants_when_parsing_then_it_returns_expected_header_and_query(
    test_case: ParseModelSqlHeaderTestCase,
) -> None:
    header_values: dict[str, object]
    query: str
    header_values, query = parse_model_sql(test_case.contents, Path("orders.sql"))

    assert header_values == test_case.expected_header_values
    assert query == test_case.expected_query


MODEL_SQL_ERROR_TEST_CASES: list[ParseModelSqlErrorTestCase] = [
    ParseModelSqlErrorTestCase(
        description="raises when the model header is missing",
        contents="SELECT 1\n",
        expected_error_fragment="must start with a MODEL",
    ),
    ParseModelSqlErrorTestCase(
        description="raises when the model body is empty",
        contents="MODEL ();\n",
        expected_error_fragment="must contain SQL after MODEL(...)",
    ),
    ParseModelSqlErrorTestCase(
        description="raises when the model header is not a mapping",
        contents="""
        MODEL ([core, finance]);

        SELECT 1
        """,
        expected_error_fragment="must define a mapping of key: value pairs",
    ),
    ParseModelSqlErrorTestCase(
        description="raises when the model header contains malformed YAML",
        contents="""
        MODEL (
          tags: [core, finance
        );

        SELECT 1
        """,
        expected_error_fragment="while parsing",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    MODEL_SQL_ERROR_TEST_CASES,
    ids=[case.description for case in MODEL_SQL_ERROR_TEST_CASES],
)
def test_given_invalid_sql_model_contents_when_parsing_then_it_raises_clear_errors(
    test_case: ParseModelSqlErrorTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        parse_model_sql(test_case.contents, Path("orders.sql"))
