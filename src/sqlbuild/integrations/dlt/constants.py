"""Constants for dlt integration loaders."""

from __future__ import annotations

from sqlbuild.adapter.types import BuiltinAdapter

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
DLT_INTEGRATION_KIND: str = "dlt"
DLT_SOURCE_TYPE_SQL_DATABASE: str = "sql_database"
DLT_SOURCE_TYPE_REST_API: str = "rest_api"
DLT_SOURCE_TYPE_FILESYSTEM: str = "filesystem"
DLT_FILESYSTEM_READER_CSV: str = "csv"
DLT_FILESYSTEM_READER_JSONL: str = "jsonl"
DLT_FILESYSTEM_READER_PARQUET: str = "parquet"
DLT_FORCE_PROGRESS_COUNTER_NAMES: frozenset[str] = frozenset({"Resources", "Files", "Jobs"})
