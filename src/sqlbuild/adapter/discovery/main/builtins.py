"""Built-in adapter registry."""

from __future__ import annotations

from sqlbuild.adapter.classes.base_adapter import BaseAdapter


def builtin_adapter_classes() -> dict[str, type[BaseAdapter]]:
    """Return built-in adapter classes keyed by adapter name."""

    from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
    from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
    from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
    from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
    from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
    from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
    from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter

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
