"""Planner domain types."""

from __future__ import annotations

from enum import StrEnum


class SelectorKind(StrEnum):
    NAME = "name"
    SEED = "seed"
    SOURCE = "source"
    TAG = "tag"
    PATH = "path"


class ChangeKind(StrEnum):
    FIRST_RUN = "first_run"
    QUERY_CHANGED = "query_changed"
    SCHEMA_CHANGED = "schema_changed"
    NO_CHANGE = "no_change"


class BackfillAction(StrEnum):
    FULL = "full"
    BOUNDED = "bounded"
    WARN_ONLY = "warn_only"


class OnSchemaChange(StrEnum):
    IGNORE = "ignore"
    FAIL = "fail"
    APPEND_NEW_COLUMNS = "append_new_columns"
    SYNC_ALL_COLUMNS = "sync_all_columns"


class SchemaChangeKind(StrEnum):
    COLUMN_ADDED = "column_added"
    COLUMN_REMOVED = "column_removed"
    COLUMN_TYPE_CHANGED = "column_type_changed"


class SchemaChangeBackfillKey(StrEnum):
    ADD_COLUMN = "add_column"
    TYPE_CHANGE = "type_change"


class SchemaColumnSource(StrEnum):
    YML = "yml"
    SQLGLOT = "sqlglot"
