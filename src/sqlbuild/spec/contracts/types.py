"""Project specification types."""

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


class TimeTravelRetentionSource(StrEnum):
    """Authored layer that supplied the effective retention policy."""

    TARGET = "target"
    MATERIALIZATION = "materialization"
    MODEL = "model"


class TimeTravelRetentionValue(StrEnum):
    """Named non-duration retention values."""

    INHERIT = "inherit"
    DISABLED = "disabled"


class TableType(StrEnum):
    """Snowflake managed table type."""

    PERMANENT = "permanent"
    TRANSIENT = "transient"


class TableTypeSource(StrEnum):
    """Authored layer that supplied the effective table type."""

    DEFAULT = "default"
    TARGET = "target"
    MATERIALIZATION = "materialization"
    MODEL = "model"


class TableTypeValue(StrEnum):
    """Named non-type table-type value."""

    INHERIT = "inherit"


class TableTypeDowngradePolicy(StrEnum):
    """Permanent-to-transient conversion policy."""

    DENY = "deny"
    REQUIRE_CONFIRMATION = "require_confirmation"
    ALLOW = "allow"
