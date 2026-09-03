"""Compute log format and policy constants."""

COMPUTE_LOG_FORMAT_VERSION: int = 1
DEFAULT_RETENTION_COUNT: int = 20
MAX_READ_BYTES: int = 1_048_576
METADATA_FILE_NAME: str = "metadata.json"
COMPLETE_FILE_NAME: str = "complete"
PRUNE_LOCK_FILE_NAME: str = ".prune.lock"
COMPLETED_AT_FIELD: str = "completed_at"
SQL_LOG_RECORD_FIELD: str = "sqlbuild_sql"
REDACTED_SQL_LOG_MESSAGE: str = "SQL diagnostic omitted"
