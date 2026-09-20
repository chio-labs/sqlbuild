"""Built-in adapter registry."""

from __future__ import annotations

from functools import cache
from importlib import import_module
from typing import cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter

_BUILTIN_ADAPTER_IMPORTS: dict[str, tuple[str, str]] = {
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


def builtin_adapter_names() -> frozenset[str]:
    """Return every reserved built-in adapter name without loading adapter implementations."""

    return frozenset(_BUILTIN_ADAPTER_IMPORTS)


@cache
def builtin_adapter_class(adapter_name: str) -> type[BaseAdapter] | None:
    """Load one built-in adapter class on demand."""

    import_spec: tuple[str, str] | None = _BUILTIN_ADAPTER_IMPORTS.get(adapter_name)
    if import_spec is None:
        return None
    module_name, class_name = import_spec
    return cast(type[BaseAdapter], getattr(import_module(module_name), class_name))


def builtin_adapter_classes() -> dict[str, type[BaseAdapter]]:
    """Return built-in adapter classes keyed by adapter name."""

    classes: dict[str, type[BaseAdapter]] = {}
    for adapter_name in _BUILTIN_ADAPTER_IMPORTS:
        adapter_class: type[BaseAdapter] | None = builtin_adapter_class(adapter_name)
        if adapter_class is not None:
            classes[adapter_name] = adapter_class
    return classes
