"""Adapter domain types."""

from __future__ import annotations

from enum import StrEnum


class BuiltinAdapter(StrEnum):
    DUCKDB = "duckdb"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    DATABRICKS = "databricks"


class CursorKind(StrEnum):
    TIMESTAMP = "timestamp"
    INTEGER = "integer"


class PromotionStrategy(StrEnum):
    ATOMIC_SWAP = "atomic_swap"
    ATOMIC_REPLACE = "atomic_replace"
    CREATE_NEW = "create_new"


class TablePromotionMode(StrEnum):
    DIRECT = "direct"
    STAGED = "staged"


class LifeCycleEventKind(StrEnum):
    SQL = "sql"
    LOG = "log"


class FrameworkType(StrEnum):
    STRING = "string"
    TIMESTAMP = "timestamp"


class TypeFamily(StrEnum):
    INTEGER = "integer"
    DECIMAL = "decimal"
    FLOAT = "float"
    STRING = "string"
    BOOLEAN = "boolean"
    TIMESTAMP = "timestamp"
    DATE = "date"
    DATETIME = "datetime"
    OTHER = "other"


class TypeDialect(StrEnum):
    BIGQUERY = "bigquery"
    SNOWFLAKE = "snowflake"
    DUCKDB = "duckdb"
    DATABRICKS = "databricks"
