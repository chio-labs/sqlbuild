"""Tests for adapter source-loader type mappings."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.helpers.builtins import builtin_adapter_classes
from sqlbuild.adapter.shared.types import BuiltinAdapter, LoaderLogicalType
from tests.unit.src.sqlbuild.adapter.shared._test_types import (
    AdapterLoaderTypeMappingTestCase,
    AdapterLoaderValueLiteralTestCase,
)

_DEFAULT_EXPECTED_TYPES: dict[LoaderLogicalType, str] = {
    LoaderLogicalType.BOOLEAN: "BOOLEAN",
    LoaderLogicalType.INTEGER: "BIGINT",
    LoaderLogicalType.FLOAT: "DOUBLE",
    LoaderLogicalType.STRING: "VARCHAR",
    LoaderLogicalType.TIMESTAMP: "TIMESTAMP",
    LoaderLogicalType.DATE: "DATE",
    LoaderLogicalType.JSON: "JSON",
}


ADAPTER_LOADER_TYPE_MAPPING_TEST_CASES: list[AdapterLoaderTypeMappingTestCase] = [
    AdapterLoaderTypeMappingTestCase(
        description="duckdb maps every loader logical type",
        adapter_name=BuiltinAdapter.DUCKDB.value,
        expected_types=_DEFAULT_EXPECTED_TYPES,
    ),
    AdapterLoaderTypeMappingTestCase(
        description="motherduck maps every loader logical type",
        adapter_name=BuiltinAdapter.MOTHERDUCK.value,
        expected_types=_DEFAULT_EXPECTED_TYPES,
    ),
    AdapterLoaderTypeMappingTestCase(
        description="bigquery maps every loader logical type",
        adapter_name=BuiltinAdapter.BIGQUERY.value,
        expected_types={
            **_DEFAULT_EXPECTED_TYPES,
            LoaderLogicalType.BOOLEAN: "BOOL",
            LoaderLogicalType.INTEGER: "INT64",
            LoaderLogicalType.FLOAT: "FLOAT64",
            LoaderLogicalType.STRING: "STRING",
        },
    ),
    AdapterLoaderTypeMappingTestCase(
        description="snowflake maps json to variant",
        adapter_name=BuiltinAdapter.SNOWFLAKE.value,
        expected_types={**_DEFAULT_EXPECTED_TYPES, LoaderLogicalType.JSON: "VARIANT"},
    ),
    AdapterLoaderTypeMappingTestCase(
        description="databricks maps strings and json to string",
        adapter_name=BuiltinAdapter.DATABRICKS.value,
        expected_types={
            **_DEFAULT_EXPECTED_TYPES,
            LoaderLogicalType.STRING: "STRING",
            LoaderLogicalType.JSON: "STRING",
        },
    ),
    AdapterLoaderTypeMappingTestCase(
        description="postgres maps text float and json to postgres types",
        adapter_name=BuiltinAdapter.POSTGRES.value,
        expected_types={
            **_DEFAULT_EXPECTED_TYPES,
            LoaderLogicalType.FLOAT: "DOUBLE PRECISION",
            LoaderLogicalType.STRING: "TEXT",
            LoaderLogicalType.JSON: "JSONB",
        },
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ADAPTER_LOADER_TYPE_MAPPING_TEST_CASES,
    ids=[case.description for case in ADAPTER_LOADER_TYPE_MAPPING_TEST_CASES],
)
def test_given_builtin_adapter_when_rendering_loader_types_then_maps_every_logical_type(
    test_case: AdapterLoaderTypeMappingTestCase,
) -> None:
    adapter_class: type[BaseAdapter] = builtin_adapter_classes()[test_case.adapter_name]
    adapter: BaseAdapter = adapter_class()

    logical_type: LoaderLogicalType
    for logical_type in LoaderLogicalType:
        assert (
            adapter.render_loader_logical_type(logical_type)
            == test_case.expected_types[logical_type]
        )


ADAPTER_LOADER_VALUE_LITERAL_TEST_CASES: list[AdapterLoaderValueLiteralTestCase] = [
    AdapterLoaderValueLiteralTestCase(
        description="duckdb renders json as quoted string literal",
        adapter_name=BuiltinAdapter.DUCKDB.value,
        value={"source": "loader's api"},
        logical_type=LoaderLogicalType.JSON,
        expected_literal="'{\"source\": \"loader''s api\"}'",
    ),
    AdapterLoaderValueLiteralTestCase(
        description="motherduck renders json as quoted string literal",
        adapter_name=BuiltinAdapter.MOTHERDUCK.value,
        value={"source": "loader's api"},
        logical_type=LoaderLogicalType.JSON,
        expected_literal="'{\"source\": \"loader''s api\"}'",
    ),
    AdapterLoaderValueLiteralTestCase(
        description="snowflake renders json with parse_json",
        adapter_name=BuiltinAdapter.SNOWFLAKE.value,
        value={"source": "loader's api"},
        logical_type=LoaderLogicalType.JSON,
        expected_literal="PARSE_JSON('{\"source\": \"loader''s api\"}')",
    ),
    AdapterLoaderValueLiteralTestCase(
        description="postgres renders json with jsonb cast",
        adapter_name=BuiltinAdapter.POSTGRES.value,
        value={"source": "loader's api"},
        logical_type=LoaderLogicalType.JSON,
        expected_literal="'{\"source\": \"loader''s api\"}'::JSONB",
    ),
    AdapterLoaderValueLiteralTestCase(
        description="bigquery renders json with json literal prefix",
        adapter_name=BuiltinAdapter.BIGQUERY.value,
        value={"source": "loader's api"},
        logical_type=LoaderLogicalType.JSON,
        expected_literal="JSON '{\"source\": \"loader''s api\"}'",
    ),
    AdapterLoaderValueLiteralTestCase(
        description="databricks renders json as quoted string literal",
        adapter_name=BuiltinAdapter.DATABRICKS.value,
        value={"source": "loader's api"},
        logical_type=LoaderLogicalType.JSON,
        expected_literal="'{\"source\": \"loader''s api\"}'",
    ),
    AdapterLoaderValueLiteralTestCase(
        description="duckdb escapes string literals",
        adapter_name=BuiltinAdapter.DUCKDB.value,
        value="customer's order",
        logical_type=LoaderLogicalType.STRING,
        expected_literal="'customer''s order'",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ADAPTER_LOADER_VALUE_LITERAL_TEST_CASES,
    ids=[case.description for case in ADAPTER_LOADER_VALUE_LITERAL_TEST_CASES],
)
def test_given_builtin_adapter_when_rendering_loader_value_then_returns_expected_literal(
    test_case: AdapterLoaderValueLiteralTestCase,
) -> None:
    adapter_class: type[BaseAdapter] = builtin_adapter_classes()[test_case.adapter_name]
    adapter: BaseAdapter = adapter_class()

    assert (
        adapter.render_loader_value_literal(
            value=test_case.value,
            logical_type=test_case.logical_type,
        )
        == test_case.expected_literal
    )
