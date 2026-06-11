"""Planner domain types."""

from __future__ import annotations

from enum import StrEnum


class SelectorKind(StrEnum):
    NAME = "name"
    SEED = "seed"
    SOURCE = "source"
    TASK = "task"
    ASSET = "asset"
    LOADER = "loader"
    CHECK = "check"
    TAG = "tag"
    PATH = "path"


class ChangeKind(StrEnum):
    FIRST_RUN = "first_run"
    QUERY_CHANGED = "query_changed"
    CONFIG_CHANGED = "config_changed"
    SCHEMA_CHANGED = "schema_changed"
    RUN_DESPITE_UNCHANGED = "run_despite_unchanged"
    NO_CHANGE = "no_change"


class BackfillAction(StrEnum):
    FULL = "full"
    BOUNDED = "bounded"
    FORWARD_ONLY = "forward"


class OnSchemaChange(StrEnum):
    IGNORE = "ignore"
    FAIL = "fail"
    APPEND_NEW_COLUMNS = "append_new_columns"
    SYNC_ALL_COLUMNS = "sync_all_columns"


class ContractPolicy(StrEnum):
    NONE = "none"
    ENFORCED = "enforced"


class SchemaChangeKind(StrEnum):
    COLUMN_ADDED = "column_added"
    COLUMN_REMOVED = "column_removed"
    COLUMN_TYPE_CHANGED = "column_type_changed"


class SchemaChangeBackfillKey(StrEnum):
    ADD_COLUMN = "add_column"
    TYPE_CHANGE = "type_change"


class SchemaColumnSource(StrEnum):
    YML = "yml"
    SQLGLOT = "sql_analysis"


class PlanAction(StrEnum):
    CREATE_VIEW = "create_view"
    CREATE_TABLE = "create_table"
    INCREMENTAL_APPEND = "incremental_append"
    INCREMENTAL_DELETE_INSERT = "incremental_delete_insert"
    INCREMENTAL_MERGE = "incremental_merge"
    SNAPSHOT = "snapshot"
    LOAD_SEED = "load_seed"
    SKIP = "skip"
    CUSTOM = "custom"


class PlanReason(StrEnum):
    FIRST_RUN = "first_run"
    FULL_REFRESH = "full_refresh"
    QUERY_CHANGED = "query_changed"
    FUNCTION_CHANGED = "function_changed"
    CONFIG_CHANGED = "config_changed"
    SCHEMA_CHANGED = "schema_changed"
    RUN_DESPITE_UNCHANGED = "run_despite_unchanged"
    UPSTREAM_CHANGED = "upstream_changed"
    NORMAL_INCREMENTAL = "normal_incremental"
    NO_CHANGE = "no_change"
    DISABLED = "disabled"


class RunDespiteUnchangedMode(StrEnum):
    ALWAYS = "always"
    DURATION = "duration"


class StandardReuseDecisionKind(StrEnum):
    REUSE_ELIGIBLE = "reuse_eligible"
    CURRENT = "current"
    REUSE_ORIGIN_FINGERPRINT_MISSING = "reuse_origin_fingerprint_missing"
    REUSE_ORIGIN_RELATION_MISSING = "reuse_origin_relation_missing"
    REUSE_ORIGIN_VERSION_MISMATCH = "reuse_origin_version_mismatch"
    REUSE_FROM_SOURCE_FRESHNESS_STALE = "reuse_from_source_freshness_stale"
    INELIGIBLE_MATERIALIZATION = "ineligible_materialization"


class RelationReuseKind(StrEnum):
    COMPLETE_RELATION_REUSE = "complete_relation_reuse"
    SEEDED_RELATION_REUSE = "seeded_relation_reuse"


class IncrementalStrategy(StrEnum):
    APPEND = "append"
    DELETE_INSERT = "delete_insert"
    MERGE = "merge"


class IncrementalMode(StrEnum):
    FULL = "full"
    MICROBATCH = "microbatch"


class SnapshotStrategy(StrEnum):
    TIMESTAMP = "timestamp"
    CHECK = "check"


class HistoricalInput(StrEnum):
    SNAPSHOT = "snapshot"
    CHANGES = "changes"


class InitialValidFrom(StrEnum):
    UPDATED_AT = "updated_at"
    OBSERVED_AT = "observed_at"
    EXECUTION_TIME = "execution_time"


class SnapshotFullRefreshPolicy(StrEnum):
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"
    ALLOW = "allow"


class SnapshotSchemaChangePolicy(StrEnum):
    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"
    APPEND_NEW_COLUMNS = "append_new_columns"


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
    SNAPSHOT = "snapshot"
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
    DBT_REF = "dbt_ref"
    MODEL = "model"
