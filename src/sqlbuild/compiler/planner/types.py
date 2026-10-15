"""Planner domain types."""

from __future__ import annotations

from enum import StrEnum


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


class RetentionDirection(StrEnum):
    INCREASE = "increase"
    DECREASE = "decrease"
    MIXED = "mixed"
    MATCH = "match"
    APPLY_AFTER_CREATE = "apply_after_create"


class RetentionPlanPhase(StrEnum):
    PRE = "pre"
    POST = "post"
    AFTER_CREATE = "after_create"
    NONE = "none"


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
    RENAMED = "renamed"
    FULL_REFRESH = "full_refresh"
    QUERY_CHANGED = "query_changed"
    FUNCTION_CHANGED = "function_changed"
    CONFIG_CHANGED = "config_changed"
    SCHEMA_CHANGED = "schema_changed"
    NORMAL_INCREMENTAL = "normal_incremental"
    NO_CHANGE = "no_change"
    DISABLED = "disabled"
    SOURCE_FRESHNESS_ERROR = "source_freshness_error"
    EXTERNAL_UPSTREAM_FAILED = "external_upstream_failed"


class IncrementalStrategy(StrEnum):
    APPEND = "append"
    DELETE_INSERT = "delete_insert"
    MERGE = "merge"


class MicrobatchStrategy(StrEnum):
    """How an ordinary microbatch range is selected."""

    ROLLING_WINDOW = "rolling_window"
    WATERMARK = "watermark"


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

    @classmethod
    def is_table_backed(cls, *, materialized: object | None) -> bool:
        """Return whether a materialization owns a physical managed table."""

        return materialized in {cls.TABLE, cls.INCREMENTAL, cls.SNAPSHOT}


class ScenarioArtifactKind(StrEnum):
    SOURCE = "source"
    REF = "ref"
    SEED = "seed"
    DBT_REF = "dbt_ref"
    MODEL = "model"
