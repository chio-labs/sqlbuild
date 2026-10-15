"""Cost observability type declarations."""

from enum import StrEnum


class CostCapability(StrEnum):
    NONE = "none"
    SNOWFLAKE_QUERY_HISTORY = "snowflake_query_history"


class CostStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    PENDING = "pending"
    UNAVAILABLE = "unavailable"
    COLLECTION_FAILED = "collection_failed"
