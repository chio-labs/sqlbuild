"""Built-in adapter registry."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.types import BuiltinAdapter


def builtin_adapter_classes() -> dict[str, type[BaseAdapter]]:
    """Return built-in adapter classes keyed by adapter name."""

    from sqlbuild.integrations.bigquery.client import BigQueryAdapter
    from sqlbuild.integrations.databricks.client import DatabricksAdapter
    from sqlbuild.integrations.duckdb.client import DuckDbAdapter
    from sqlbuild.integrations.motherduck.client import MotherDuckAdapter
    from sqlbuild.integrations.postgres.client import PostgresAdapter
    from sqlbuild.integrations.snowflake.client import SnowflakeAdapter
    from sqlbuild.integrations.sqlserver.client import SqlServerAdapter

    return {
        BuiltinAdapter.DUCKDB.value: DuckDbAdapter,
        BuiltinAdapter.MOTHERDUCK.value: MotherDuckAdapter,
        BuiltinAdapter.SNOWFLAKE.value: SnowflakeAdapter,
        BuiltinAdapter.BIGQUERY.value: BigQueryAdapter,
        BuiltinAdapter.DATABRICKS.value: DatabricksAdapter,
        BuiltinAdapter.POSTGRES.value: PostgresAdapter,
        BuiltinAdapter.SQLSERVER.value: SqlServerAdapter,
    }
