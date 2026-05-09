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


class PlanAction(StrEnum):
    CREATE_VIEW = "create_view"
    CREATE_TABLE = "create_table"
    INCREMENTAL_APPEND = "incremental_append"
    INCREMENTAL_DELETE_INSERT = "incremental_delete_insert"
    INCREMENTAL_MERGE = "incremental_merge"
    LOAD_SEED = "load_seed"
    SKIP = "skip"
    CUSTOM = "custom"


class PlanReason(StrEnum):
    FIRST_RUN = "first_run"
    FULL_REFRESH = "full_refresh"
    QUERY_CHANGED = "query_changed"
    SCHEMA_CHANGED = "schema_changed"
    UPSTREAM_CHANGED = "upstream_changed"
    NORMAL_INCREMENTAL = "normal_incremental"
    NO_CHANGE = "no_change"
    DISABLED = "disabled"


class IncrementalStrategy(StrEnum):
    APPEND = "append"
    DELETE_INSERT = "delete_insert"
    MERGE = "merge"


class IncrementalMode(StrEnum):
    FULL = "full"
    MICROBATCH = "microbatch"


class CursorType(StrEnum):
    TIMESTAMP = "timestamp"
    INTEGER = "integer"


class CursorGrain(StrEnum):
    SECOND = "second"
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"
    YEAR = "year"


class MaterializationType(StrEnum):
    VIEW = "view"
    TABLE = "table"
    INCREMENTAL = "incremental"
    SEED = "seed"
    CUSTOM = "custom"


class SchemaActionKind(StrEnum):
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    ALTER_COLUMN_TYPE = "alter_column_type"


class WarningSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ScenarioArtifactKind(StrEnum):
    SOURCE = "source"
    REF = "ref"
    SEED = "seed"
    MODEL = "model"
