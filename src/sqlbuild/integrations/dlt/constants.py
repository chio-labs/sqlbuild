"""Constants for dlt integration loaders."""

from __future__ import annotations

from sqlbuild.adapter.shared.types import BuiltinAdapter

DLT_DESTINATION_ADAPTERS: frozenset[BuiltinAdapter] = frozenset(
    {
        BuiltinAdapter.DUCKDB,
        BuiltinAdapter.MOTHERDUCK,
        BuiltinAdapter.SNOWFLAKE,
        BuiltinAdapter.BIGQUERY,
        BuiltinAdapter.DATABRICKS,
        BuiltinAdapter.POSTGRES,
        BuiltinAdapter.SQLSERVER,
    }
)
