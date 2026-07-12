"""Adapter domain types."""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Protocol

from sqlbuild.compiler.lineage.types import InferredNullability

type FunctionNullabilityRule = Callable[[tuple[InferredNullability, ...]], InferredNullability]


class AdapterExecute[ConnectionT, ResultT](Protocol):
    def __call__(self, *, connection: ConnectionT, sql: str) -> ResultT: ...


class BuiltinAdapter(StrEnum):
    DUCKDB = "duckdb"
    MOTHERDUCK = "motherduck"
    SNOWFLAKE = "snowflake"
    BIGQUERY = "bigquery"
    DATABRICKS = "databricks"
    POSTGRES = "postgres"
    SQLSERVER = "sqlserver"


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


class RelationType(StrEnum):
    TABLE = "table"
    VIEW = "view"
    OTHER = "other"


class LifeCycleEventKind(StrEnum):
    SQL = "sql"
    LOG = "log"


class FrameworkType(StrEnum):
    STRING = "string"
    TIMESTAMP = "timestamp"


class LoaderLogicalType(StrEnum):
    BOOLEAN = "boolean"
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    TIMESTAMP = "timestamp"
    DATE = "date"
    JSON = "json"


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
    GENERIC = "generic"
    BIGQUERY = "bigquery"
    SNOWFLAKE = "snowflake"
    DUCKDB = "duckdb"
    MOTHERDUCK = "motherduck"
    DATABRICKS = "databricks"
    POSTGRES = "postgres"
    TSQL = "tsql"
