"""Stable archive state constants."""

ARCHIVE_EVENT_TABLE_NAME: str = "_sqlbuild_archive_events"
ARCHIVE_NAME_PREFIX: str = "__sqb_archive__"
ARCHIVE_TIMESTAMP_FORMAT: str = "%Y%m%dT%H%M%S%fZ"
ARCHIVE_WRITE_ATTEMPTS: int = 3
ARCHIVE_WRITE_RETRY_BASE_SECONDS: float = 0.05

ARCHIVE_INTEGER_COLUMNS: frozenset[str] = frozenset({"retention_days"})
ARCHIVE_EVENT_COLUMNS: tuple[str, ...] = (
    "event_id",
    "record_type",
    "requirement_id",
    "operation_kind",
    "target_database",
    "target_schema",
    "target_name",
    "source_physical_generation",
    "archive_name",
    "archive_physical_generation",
    "origin_run_id",
    "execution_run_id",
    "provenance_status",
    "synthetic_reason",
    "retention_days",
    "requested_at",
    "completed_at",
    "observed_at",
    "created_at",
)
