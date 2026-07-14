"""dbt pipeline constants."""

DBT_BOUNDED_FLAG: str = "--bounded"
DBT_CLONE_POSITIONAL_SELECT_TOKEN: str = "select"
DBT_DEFER_FLAG: str = "--defer"
DBT_DIFF_DAY_UNIT: str = "d"
DBT_DIFF_HOUR_UNIT: str = "h"
DBT_DIFF_MINUTE_UNIT: str = "m"
DBT_EXECUTION_FAIL_STATUSES: frozenset[str] = frozenset({"error", "fail", "failed"})
DBT_EXECUTION_SKIP_STATUSES: frozenset[str] = frozenset({"skip", "skipped"})
DBT_EXECUTION_SUCCESS_STATUSES: frozenset[str] = frozenset(
    {"ok", "success", "pass", "passed", "warn", "warning"}
)
DBT_EXECUTION_WARN_STATUSES: frozenset[str] = frozenset({"warn", "warning"})
DBT_EXCLUDE_FLAG: str = "--exclude"
DBT_FORCE_FLAG: str = "--force"
DBT_FULL_FLAG: str = "--full"
DBT_FULL_REFRESH_FLAG: str = "--full-refresh"
DBT_HARD_COPY_FLAG: str = "--hard-copy"
DBT_MAX_COLUMN_EXAMPLES_FLAG: str = "--max-column-examples"
DBT_MAX_ROW_ONLY_EXAMPLES_FLAG: str = "--max-row-only-examples"
DBT_NO_SQL_VALIDATION_FLAG: str = "--no-sql-validation"
DBT_REPLAY_FULL: str = "full"
DBT_REPLAY_FORWARD_ONLY: str = "forward_only"
DBT_REPLAY_NOOP_POLICIES: frozenset[str] = frozenset({"", "forward_only"})
DBT_SCHEMA_ONLY_FLAG: str = "--schema-only"
DBT_SELECT_FLAGS: frozenset[str] = frozenset({"--select", "-s"})
DBT_SELECT_FLAG: str = "--select"
DBT_SELECTION_FLAGS: frozenset[str] = frozenset({"--select", "--exclude"})
DBT_UNIQUE_ID_SEPARATOR: str = "."
DBT_VERBOSE_FLAGS: frozenset[str] = frozenset({"--verbose", "-v"})
