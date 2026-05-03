"""Adapter domain types."""

from __future__ import annotations

from enum import StrEnum


class BuiltinAdapter(StrEnum):
    DUCKDB = "duckdb"
    SNOWFLAKE = "snowflake"


class CursorKind(StrEnum):
    TIMESTAMP = "timestamp"
    INTEGER = "integer"


class PromotionStrategy(StrEnum):
    ATOMIC_SWAP = "atomic_swap"
    ATOMIC_REPLACE = "atomic_replace"
    CREATE_NEW = "create_new"


class LifeCycleEventKind(StrEnum):
    SQL = "sql"
    LOG = "log"
