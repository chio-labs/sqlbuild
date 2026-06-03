"""Shared spec type aliases."""

from __future__ import annotations

from enum import StrEnum

type PathDefaultsMap = dict[str, dict[str, object]]


class SourceWriteStrategy(StrEnum):
    APPEND = "append"
    DELETE_INSERT = "delete_insert"
    MERGE = "merge"
    TABLE = "table"


class SourceFreshnessStrategy(StrEnum):
    ADAPTER = "adapter"
    COLUMN = "column"
    SQL = "sql"


class SourceFreshnessValueKind(StrEnum):
    TIMESTAMP = "timestamp"
    INTEGER = "integer"
    STRING = "string"
