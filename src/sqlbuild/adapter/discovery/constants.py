"""Built-in adapter discovery constants."""

BUILTIN_ADAPTER_IMPORTS: dict[str, tuple[str, str]] = {
    "duckdb": ("sqlbuild.adapters.duckdb.classes.duckdb_adapter", "DuckDbAdapter"),
    "motherduck": (
        "sqlbuild.adapters.motherduck.classes.motherduck_adapter",
        "MotherDuckAdapter",
    ),
    "snowflake": (
        "sqlbuild.adapters.snowflake.classes.snowflake_adapter",
        "SnowflakeAdapter",
    ),
    "bigquery": ("sqlbuild.adapters.bigquery.classes.bigquery_adapter", "BigQueryAdapter"),
    "databricks": (
        "sqlbuild.adapters.databricks.classes.databricks_adapter",
        "DatabricksAdapter",
    ),
    "postgres": ("sqlbuild.adapters.postgres.classes.postgres_adapter", "PostgresAdapter"),
    "sqlserver": (
        "sqlbuild.adapters.sqlserver.classes.sqlserver_adapter",
        "SqlServerAdapter",
    ),
}
