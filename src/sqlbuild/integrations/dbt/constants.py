"""dbt integration constants."""

from sqlbuild.integrations.dbt.types import DbtInteropCommand

DBT_EXECUTION_COMMANDS: frozenset[DbtInteropCommand] = frozenset(
    (
        DbtInteropCommand.PLAN,
        DbtInteropCommand.RUN,
        DbtInteropCommand.BUILD,
        DbtInteropCommand.TEST,
    )
)
DBT_EXECUTION_DISPLAY_FLAGS: frozenset[str] = frozenset(("--json", "--verbose", "-v"))
DBT_SUCCESSFUL_RESULT_STATUSES: frozenset[str] = frozenset({"ok", "success", "pass", "passed"})

DBT_MANIFEST_CONFIG_KEY: str = "config"
DBT_MANIFEST_INCREMENTAL_STRATEGY_KEY: str = "incremental_strategy"
DBT_MANIFEST_MATERIALIZED_KEY: str = "materialized"
DBT_MANIFEST_META_KEY: str = "meta"
DBT_MANIFEST_RESOURCE_TYPE_KEY: str = "resource_type"
DBT_MANIFEST_SQLBUILD_META_KEY: str = "sqlbuild"

DBT_EXECUTABLE_ENV_VAR: str = "DBT_EXECUTABLE"
DEFAULT_DBT_EXECUTABLE: str = "dbt"

DBT_DEFINITION_FINGERPRINT_EXCLUDED_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "schema",
        "database",
        "alias",
        "target_schema",
        "target_database",
        "tags",
        "docs",
        "group",
        "enabled",
        "packages",
    }
)

DBT_MATERIALIZATION_EPHEMERAL: str = "ephemeral"
DBT_MATERIALIZATION_INCREMENTAL: str = "incremental"
DBT_MATERIALIZATION_MICROBATCH: str = "microbatch"
DBT_MATERIALIZATION_SNAPSHOT: str = "snapshot"
DBT_MATERIALIZATION_TABLE: str = "table"
DBT_MATERIALIZATION_VIEW: str = "view"

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
DBT_CHANGES_ONLY_FLAG: str = "--changes-only"
DBT_FULL_FLAG: str = "--full"
DBT_FULL_REFRESH_FLAG: str = "--full-refresh"
DBT_HARD_COPY_FLAG: str = "--hard-copy"
DBT_MAX_COLUMN_EXAMPLES_FLAG: str = "--max-column-examples"
DBT_MAX_ROW_ONLY_EXAMPLES_FLAG: str = "--max-row-only-examples"
DBT_NO_SQL_VALIDATION_FLAG: str = "--no-sql-validation"
DBT_PATH_SELECTOR_SEPARATOR: str = "~"
DBT_REPLAY_FULL: str = "full"
DBT_REPLAY_FORWARD_ONLY: str = "forward_only"
DBT_REPLAY_NOOP_POLICIES: frozenset[str] = frozenset({"", "forward_only"})
DBT_SCHEMA_ONLY_FLAG: str = "--schema-only"
DBT_SELECT_FLAGS: frozenset[str] = frozenset({"--select", "-s"})
DBT_SELECT_FLAG: str = "--select"
DBT_SELECTION_FLAGS: frozenset[str] = frozenset({"--select", "--exclude"})
DBT_UNIQUE_ID_SEPARATOR: str = "."
DBT_VERBOSE_FLAGS: frozenset[str] = frozenset({"--verbose", "-v"})
