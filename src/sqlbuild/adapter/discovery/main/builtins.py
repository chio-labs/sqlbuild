"""Built-in adapter registry."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter


def builtin_adapter_classes() -> dict[str, type[BaseAdapter]]:
    """Return built-in adapter classes keyed by adapter name."""

    from sqlbuild.adapters.bigquery.client import BigQueryAdapter
    from sqlbuild.adapters.databricks.client import DatabricksAdapter
    from sqlbuild.adapters.duckdb.client import DuckDbAdapter
    from sqlbuild.adapters.motherduck.client import MotherDuckAdapter
    from sqlbuild.adapters.postgres.client import PostgresAdapter
    from sqlbuild.adapters.snowflake.client import SnowflakeAdapter
    from sqlbuild.adapters.sqlserver.client import SqlServerAdapter

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
