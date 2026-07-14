"""dbt runtime event constants."""

DBT_ERROR_LEVEL: str = "error"
DBT_NODE_FINISHED_EVENT: str = "NodeFinished"
DBT_NODE_MESSAGE_EVENT_NAMES: frozenset[str] = frozenset(
    {"RunResultError", "RunResultFailure", "RunResultWarning", "GenericExceptionOnRun"}
)
DBT_NODE_MESSAGE_LEVELS: frozenset[str] = frozenset({"warn", "error"})
DBT_NODE_STARTED_EVENT_NAMES: frozenset[str] = frozenset({"LogStartLine", "NodeStarted"})
DBT_OUTCOME_STATUSES: frozenset[str] = frozenset(
    {
        "error",
        "fail",
        "failed",
        "ok",
        "pass",
        "passed",
        "skip",
        "skipped",
        "success",
        "warn",
        "warning",
    }
)
DBT_RESULT_EVENT_NAMES: frozenset[str] = frozenset(
    {
        "LogModelResult",
        "LogSeedResult",
        "LogSnapshotResult",
        "LogTestResult",
        "LogBatchResult",
        "LogFunctionResult",
        "NodeFinished",
    }
)
DBT_SOURCE_FRESHNESS_DAY_PERIODS: frozenset[str] = frozenset({"day", "days"})
DBT_SOURCE_FRESHNESS_HOUR_PERIODS: frozenset[str] = frozenset({"hour", "hours"})
DBT_SOURCE_FRESHNESS_MINUTE_PERIODS: frozenset[str] = frozenset({"minute", "minutes"})
DBT_START_STATUSES: frozenset[str] = frozenset({"start"})
DBT_STATUS_ERROR_VALUES: frozenset[str] = frozenset({"error", "fail", "failed"})
DBT_STATUS_OK_VALUES: frozenset[str] = frozenset({"ok", "success"})
DBT_STATUS_PASS_VALUES: frozenset[str] = frozenset({"pass", "passed"})
DBT_STATUS_SKIP_VALUES: frozenset[str] = frozenset({"skip", "skipped"})
DBT_STATUS_WARN_VALUES: frozenset[str] = frozenset({"warn", "warning"})
DBT_WARN_LEVEL: str = "warn"
