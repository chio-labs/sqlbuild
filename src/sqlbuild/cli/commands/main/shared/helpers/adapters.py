"""Adapter resolution from project configuration."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.types import BuiltinAdapter


def resolve_adapter(adapter_name: str) -> BaseAdapter:
    """Resolve an adapter name from project config to a built-in adapter instance."""

    match adapter_name:
        case BuiltinAdapter.DUCKDB:
            from sqlbuild.integrations.duckdb.client import DuckDbAdapter

            return DuckDbAdapter()
        case BuiltinAdapter.SNOWFLAKE:
            from sqlbuild.integrations.snowflake.client import SnowflakeAdapter

            return SnowflakeAdapter()
        case BuiltinAdapter.BIGQUERY:
            from sqlbuild.integrations.bigquery.client import BigQueryAdapter

            return BigQueryAdapter()
        case BuiltinAdapter.DATABRICKS:
            from sqlbuild.integrations.databricks.client import DatabricksAdapter

            return DatabricksAdapter()
        case _:
            available: str = ", ".join(a.value for a in BuiltinAdapter)
            raise ValueError(
                f"Unknown adapter '{adapter_name}'. Available built-in adapters: {available}"
            )
