"""Built-in adapter registry."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter


def builtin_adapter_classes() -> dict[str, type[BaseAdapter]]:
    """Return built-in adapter classes keyed by adapter name."""

    from sqlbuild.integrations.bigquery.client import BigQueryAdapter
    from sqlbuild.integrations.databricks.client import DatabricksAdapter
    from sqlbuild.integrations.duckdb.client import DuckDbAdapter
    from sqlbuild.integrations.motherduck.client import MotherDuckAdapter
    from sqlbuild.integrations.postgres.client import PostgresAdapter
    from sqlbuild.integrations.snowflake.client import SnowflakeAdapter
    from sqlbuild.integrations.sqlserver.client import SqlServerAdapter

    adapters: tuple[type[BaseAdapter], ...] = (
        DuckDbAdapter,
        MotherDuckAdapter,
        SnowflakeAdapter,
        BigQueryAdapter,
        DatabricksAdapter,
        PostgresAdapter,
        SqlServerAdapter,
    )
    return {adapter.adapter_name: adapter for adapter in adapters}
