"""Execution history contract limits and schema defaults."""

DEFAULT_PAGE_LIMIT: int = 100
MAX_PAGE_LIMIT: int = 1000
CURRENT_EVENT_LOG_SCHEMA_VERSION: int = 1
CURRENT_RUN_STORAGE_SCHEMA_VERSION: int = 1
RUN_STARTED_EVENT_TYPE: str = "run_started"
RUN_COMPLETED_EVENT_TYPE: str = "run_completed"
RUN_FAILED_EVENT_TYPE: str = "run_failed"
