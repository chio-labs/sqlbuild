"""Adapter domain types."""

from __future__ import annotations

from enum import StrEnum


class BuiltinAdapter(StrEnum):
    DUCKDB = "duckdb"


class CursorKind(StrEnum):
    TIMESTAMP = "timestamp"
    INTEGER = "integer"
